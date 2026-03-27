import os
import subprocess
import sys
import tempfile
import time

# Check Windows compatibility
if os.name != 'nt':
    print("This script is compatible only with Windows.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAX_RETRIES   = 5      # how many times to retry a failed command
RETRY_DELAY   = 3.0   # initial wait in seconds before first retry
RETRY_BACKOFF = 2.0   # multiply delay by this factor on each subsequent retry
NTFSMARKBAD   = "NTFSMARKBAD.exe"
BADS_FILE     = "bads.txt"
# ---------------------------------------------------------------------------


def run_with_retry(command: list[str], label: str) -> bool:
    """
    Run *command* (as a list) with up to MAX_RETRIES retries.
    Returns True on success, False if all attempts failed.
    """
    delay = RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            return True, result.stdout.strip()

        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"

        if attempt < MAX_RETRIES:
            print(f"  [{label}] attempt {attempt}/{MAX_RETRIES} failed: {detail}")
            print(f"  Retrying in {delay:.0f}s  (Explorer may be holding the volume)...")
            time.sleep(delay)
            delay *= RETRY_BACKOFF
        else:
            print(f"  [{label}] all {MAX_RETRIES} attempts failed. Last error: {detail}")

    return False, ""


def parse_bads(path: str) -> list[tuple[int, int]]:
    """
    Parse bads.txt and return a list of (start_sector, end_sector) tuples.
    Lines are: sector_value,multiplier[;optional comment]
    end_sector = sector_value + multiplier   (matches original behaviour)
    """
    entries: list[tuple[int, int]] = []
    with open(path, "r") as f:
        for raw_line in f:
            line = raw_line.split(";")[0].strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 2:
                print(f"  Skipping malformed line: {raw_line.rstrip()}")
                continue
            try:
                sector_value = int(parts[0])
                multiplier   = int(parts[1])
                entries.append((sector_value, sector_value + multiplier))
            except ValueError:
                print(f"  Skipping non-numeric line: {raw_line.rstrip()}")
    return entries


def write_batch_file(entries: list[tuple[int, int]], path: str):
    """Write sector pairs to a batch file in the format expected by /B mode."""
    with open(path, "w") as f:
        for start, end in entries:
            f.write(f"{start} {end}\n")


def run_batch_mode(drive: str, entries: list[tuple[int, int]]) -> bool:
    """
    Attempt to mark all bad clusters in a single NTFSMARKBAD /B invocation.
    Returns True if it succeeded.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, prefix="ntfsray_batch_") as tmp:
        batch_path = tmp.name
        for start, end in entries:
            tmp.write(f"{start} {end}\n")

    print(f"Batch file written: {batch_path}  ({len(entries)} entries)")
    print(f"Running: {NTFSMARKBAD} {drive} /B {batch_path}\n")

    try:
        ok, stdout = run_with_retry([NTFSMARKBAD, drive, "/B", batch_path],
                                    label="batch")
        if ok:
            print(stdout)
            return True
        return False
    finally:
        try:
            os.unlink(batch_path)
        except OSError:
            pass


def run_individual_mode(drive: str, entries: list[tuple[int, int]]):
    """
    Fall-back: process each entry individually with retry.
    Reports per-entry success/failure.
    """
    failed: list[int] = []
    total = len(entries)

    for idx, (start, end) in enumerate(entries, start=1):
        cmd   = [NTFSMARKBAD, drive, str(start), str(end)]
        label = f"{idx}/{total}"
        print(f"[{label}] Running: {' '.join(cmd)}")

        ok, stdout = run_with_retry(cmd, label=label)
        if ok:
            # Print only the first line of NTFSMARKBAD's verbose output to keep
            # things readable; full output is usually many lines of scanning info.
            first_line = stdout.splitlines()[0] if stdout else "(no output)"
            print(f"  ✓ {first_line}")
        else:
            failed.append(idx)

    print(f"\n{'─'*60}")
    print(f"Individual mode complete. {total - len(failed)}/{total} entries succeeded.")
    if failed:
        print(f"Failed entries (1-based line numbers): {failed}")
    else:
        print("All entries processed successfully. Congratulations!")


def main():
    print("=" * 60)
    print("  NTFSRAY  –  bad-sector marker wrapper")
    print("  Tool: https://github.com/jamersonpro/ntfsmarkbad")
    print("=" * 60 + "\n")

    # --- sanity checks ---
    if not os.path.exists(NTFSMARKBAD):
        print(f"Error: '{NTFSMARKBAD}' not found in the current directory.")
        sys.exit(1)

    if not os.path.exists(BADS_FILE):
        print(f"Error: '{BADS_FILE}' not found.")
        sys.exit(1)

    # --- parse input ---
    entries = parse_bads(BADS_FILE)
    if not entries:
        print("No valid entries found in bads.txt. Nothing to do.")
        sys.exit(0)
    print(f"Parsed {len(entries)} entries from {BADS_FILE}.\n")

    # --- drive letter ---
    drive_letter = input("Enter the drive letter (e.g., 'R'): ").strip().upper()
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        print("Error: Invalid drive letter.")
        sys.exit(1)
    drive = drive_letter + ":"

    print(f"\nTarget drive : {drive}")
    print(f"Max retries  : {MAX_RETRIES}  (delay starts at {RETRY_DELAY}s, ×{RETRY_BACKOFF} each attempt)")
    print()

    # --- try batch mode first ---
    print("── Batch mode ─────────────────────────────────────────────")
    batch_ok = run_batch_mode(drive, entries)

    if batch_ok:
        print("\nBatch mode succeeded. All done!")
        return

    # --- fall back to individual mode ---
    print("\nBatch mode failed (possibly a volume-lock race with Explorer).")
    print("Falling back to individual entry mode with retry...\n")
    print("── Individual mode ─────────────────────────────────────────")
    run_individual_mode(drive, entries)


if __name__ == "__main__":
    main()
