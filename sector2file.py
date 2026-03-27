import os
import subprocess
import sys
import re
import argparse

if os.name != 'nt':
    print("This script is compatible only with Windows.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NTFSMARKBAD = "NTFSMARKBAD.exe"
NFI_EXE     = "nfi.exe"
# ---------------------------------------------------------------------------

VOL_FIRST_RE  = re.compile(r"First volume sector:\s*(\d+)")
VOL_LAST_RE   = re.compile(r"Last volume sector:\s*(\d+)")
BPS_RE        = re.compile(r"Bytes per sector:\s*(\d+)")
SPC_RE        = re.compile(r"Sectors per cluster:\s*(\d+)")
CLUSTERS_RE   = re.compile(r"Total cluster count:\s*(\d+)")


def get_volume_info(drive: str, verbose: bool) -> dict | None:
    """Run NTFSMARKBAD <drive>: with no sector args to get volume metadata."""
    result = subprocess.run([NTFSMARKBAD, drive], capture_output=True, text=True)
    out = result.stdout + result.stderr

    info = {}
    for label, pattern in [
        ("first_sector", VOL_FIRST_RE),
        ("last_sector",  VOL_LAST_RE),
        ("bytes_per_sector", BPS_RE),
        ("sectors_per_cluster", SPC_RE),
        ("total_clusters", CLUSTERS_RE),
    ]:
        m = pattern.search(out)
        if m:
            info[label] = int(m.group(1))
        else:
            print(f"Error: could not parse '{label}' from NTFSMARKBAD output.")
            if verbose:
                print("--- NTFSMARKBAD output ---")
                print(out)
            return None

    if verbose:
        print("Volume info from NTFSMARKBAD:")
        print(f"  First sector       : {info['first_sector']}")
        print(f"  Last sector        : {info['last_sector']}")
        print(f"  Bytes per sector   : {info['bytes_per_sector']}")
        print(f"  Sectors per cluster: {info['sectors_per_cluster']}")
        print(f"  Total clusters     : {info['total_clusters']}")
        size_gb = (info['last_sector'] - info['first_sector']) * info['bytes_per_sector'] / 1e9
        print(f"  Volume size        : {size_gb:.1f} GB")
        print()

    return info


def query_nfi(drive_letter: str, logical_sector: int, verbose: bool) -> str:
    """Run nfi.exe <drive>: <logical_sector> and return its output."""
    cmd = [NFI_EXE, drive_letter + ":", str(logical_sector)]
    if verbose:
        print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout + result.stderr


def parse_nfi_output(output: str) -> list[str]:
    """
    Extract file/path info from nfi output.
    nfi prints lines like:
      \path\to\file
    or mentions file record numbers, MFT entries, etc.
    We collect any line that looks like a path or a file record reference.
    """
    lines = []
    for line in output.splitlines():
        s = line.strip()
        if not s:
            continue
        # nfi outputs paths starting with backslash, or "File X" lines
        if s.startswith("\\") or re.match(r"(?i)file\s+\d+", s) or re.match(r"(?i)\$", s):
            lines.append(s)
    return lines if lines else ["(nfi returned no file information)"]


def sector_to_logical(physical_sector: int, first_volume_sector: int) -> int:
    return physical_sector - first_volume_sector


def main():
    parser = argparse.ArgumentParser(
        description="Find files occupying specific sectors on an NTFS volume."
    )
    parser.add_argument("drive", nargs="?", help="Drive letter (e.g. R)")
    parser.add_argument(
        "sectors", nargs="*", type=int,
        help="One or more physical start sectors to look up (space-separated). "
             "If omitted, the script asks interactively."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show volume info and raw nfi output"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  sector2file  –  map sectors to NTFS files via nfi.exe")
    print("=" * 60 + "\n")

    # --- sanity checks ---
    for exe in (NTFSMARKBAD, NFI_EXE):
        if not os.path.exists(exe):
            print(f"Error: '{exe}' not found in current directory.")
            sys.exit(1)

    # --- drive letter ---
    drive_letter = args.drive
    if not drive_letter:
        drive_letter = input("Enter the drive letter (e.g., 'R'): ").strip().upper()
    else:
        drive_letter = drive_letter.strip().upper().rstrip(":")
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        print("Error: Invalid drive letter.")
        sys.exit(1)
    drive = drive_letter + ":"

    # --- get volume info ---
    print(f"Querying volume info for {drive} ...")
    info = get_volume_info(drive, args.verbose)
    if info is None:
        sys.exit(1)
    first_sector = info["first_sector"]
    spc          = info["sectors_per_cluster"]
    bps          = info["bytes_per_sector"]
    cluster_size = spc * bps

    if not args.verbose:
        print(f"  Volume offset : sector {first_sector}  "
              f"({bps} B/sector, {spc} sectors/cluster = {cluster_size // 1024} KB clusters)\n")

    # --- sector list ---
    physical_sectors = args.sectors
    if not physical_sectors:
        raw = input(
            "Enter physical start sector(s) to look up (space-separated): "
        ).strip()
        try:
            physical_sectors = [int(x) for x in raw.split()]
        except ValueError:
            print("Error: expected integer sector numbers.")
            sys.exit(1)

    if not physical_sectors:
        print("No sectors provided. Nothing to do.")
        sys.exit(0)

    print()
    results: list[dict] = []

    for phys in physical_sectors:
        logical = sector_to_logical(phys, first_sector)
        # cluster that contains this sector
        cluster_idx = logical // spc
        offset_in_cluster = logical % spc

        print(f"── Sector {phys} {'─' * max(0, 45 - len(str(phys)))}")
        print(f"   Logical sector  : {logical}")
        print(f"   Cluster index   : {cluster_idx}  (offset {offset_in_cluster} sectors into cluster)")

        nfi_out = query_nfi(drive_letter, logical, args.verbose)

        if args.verbose:
            print("  --- nfi raw output ---")
            for line in nfi_out.splitlines():
                if line.strip():
                    print(f"  {line}")
            print()

        files = parse_nfi_output(nfi_out)
        print(f"   File(s) found:")
        for f in files:
            print(f"     {f}")

        results.append({
            "physical": phys,
            "logical":  logical,
            "cluster":  cluster_idx,
            "files":    files,
            "raw_nfi":  nfi_out,
        })
        print()

    # --- summary ---
    print("=" * 60)
    print("Summary\n")
    for r in results:
        label = ", ".join(r["files"])
        print(f"  Sector {r['physical']:>12}  →  {label}")

    print("\nDone.")


if __name__ == "__main__":
    main()
