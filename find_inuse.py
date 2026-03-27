import os
import subprocess
import sys
import time
import re

if os.name != 'nt':
    print("This script is compatible only with Windows.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_RETRIES   = 5
RETRY_DELAY   = 3.0
RETRY_BACKOFF = 2.0
NTFSMARKBAD   = "NTFSMARKBAD.exe"
BADS_FILE     = "bads.txt"
# ---------------------------------------------------------------------------

INUSE_RE  = re.compile(r"clusters skipped since they are in use:\s*(\d+)", re.IGNORECASE)
LOCK_RE   = re.compile(r"cannot lock", re.IGNORECASE)


def parse_bads(path: str) -> list[tuple[int, int, str]]:
    """Returns list of (start, end, original_line)."""
    entries = []
    with open(path, "r") as f:
        for raw in f:
            clean = raw.split(";")[0].strip()
            if not clean:
                continue
            parts = clean.split(",")
            if len(parts) != 2:
                continue
            try:
                start = int(parts[0].strip())
                mult  = int(parts[1].strip())
                entries.append((start, start + mult, raw.rstrip()))
            except ValueError:
                continue
    return entries


def run_entry(drive: str, start: int, end: int) -> tuple[bool, str]:
    """
    Run NTFSMARKBAD for one entry with retry.
    Returns (got_clean_output, combined_stdout).
    Retries on lock errors; gives up after MAX_RETRIES.
    """
    delay = RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        result = subprocess.run(
            [NTFSMARKBAD, drive, str(start), str(end)],
            capture_output=True, text=True
        )
        output = result.stdout + result.stderr

        if LOCK_RE.search(output):
            if attempt < MAX_RETRIES:
                print(f"    lock error, retry {attempt}/{MAX_RETRIES} in {delay:.0f}s...")
                time.sleep(delay)
                delay *= RETRY_BACKOFF
                continue
            else:
                return False, output   # gave up
        return True, output            # clean run (may or may not have in-use clusters)

    return False, ""


def main():
    print("=" * 60)
    print("  find_inuse  –  locate in-use clusters in bads.txt")
    print("=" * 60 + "\n")

    if not os.path.exists(NTFSMARKBAD):
        print(f"Error: '{NTFSMARKBAD}' not found.")
        sys.exit(1)
    if not os.path.exists(BADS_FILE):
        print(f"Error: '{BADS_FILE}' not found.")
        sys.exit(1)

    entries = parse_bads(BADS_FILE)
    if not entries:
        print("No valid entries found.")
        sys.exit(0)

    drive_letter = input("Enter the drive letter (e.g., 'R'): ").strip().upper()
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        print("Error: Invalid drive letter.")
        sys.exit(1)
    drive = drive_letter + ":"

    print(f"\nScanning {len(entries)} entries on {drive} ...\n")

    found:   list[tuple[int, int, str, int]] = []   # (start, end, orig_line, count)
    failed:  list[tuple[int, int, str]]      = []   # could not lock after retries
    total = len(entries)

    for idx, (start, end, orig) in enumerate(entries, 1):
        print(f"[{idx:>3}/{total}] {start} – {end}", end="  ", flush=True)
        ok, output = run_entry(drive, start, end)

        if not ok:
            print("✗ lock failed after retries")
            failed.append((start, end, orig))
            continue

        m = INUSE_RE.search(output)
        count = int(m.group(1)) if m else 0

        if count > 0:
            print(f"⚠  IN USE ({count} cluster{'s' if count != 1 else ''})")
            found.append((start, end, orig, count))
        else:
            print("✓")

    # --- summary ---
    print("\n" + "=" * 60)
    if found:
        print(f"IN-USE entries ({len(found)} found):\n")
        for start, end, orig, count in found:
            logical_start = start - 32768   # subtract volume offset
            print(f"  sectors {start}–{end}  ({count} cluster{'s' if count != 1 else ''})")
            print(f"    original line : {orig}")
            print(f"    nfi command   : nfi.exe {drive_letter}: {logical_start}")
            print()
    else:
        print("No in-use clusters found.")

    if failed:
        print(f"\nEntries that could not be checked (lock failed):")
        for start, end, orig in failed:
            print(f"  {start}–{end}  ({orig})")

    print("\nDone.")


if __name__ == "__main__":
    main()
