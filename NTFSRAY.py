import os
import subprocess
import sys

# Check Windows compatibility
if os.name != 'nt':
    print("This script is compatible only with Windows.")
    sys.exit(1)

def main():
    # Provide info about the tool
    print("This script uses the NTFSMARKBAD tool to mark bad sectors.")
    print("Ensure 'NTFSMARKBAD.exe' is in the same directory as this script.")
    print("Tool URL: https://github.com/jamersonpro/ntfsmarkbad\n")

    # Verify if NTFSMARKBAD.exe exists
    if not os.path.exists("NTFSMARKBAD.exe"):
        print("Error: 'NTFSMARKBAD.exe' is not found in the current directory.")
        sys.exit(1)

    # Read the bads.txt file
    try:
        with open("bads.txt", "r") as file:
            lines = file.readlines()
    except FileNotFoundError:
        print("Error: 'bads.txt' file not found.")
        sys.exit(1)

    # Ask the user for the drive letter
    drive_letter = input("Enter the drive letter (e.g., 'E'): ").strip().upper()
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        print("Error: Invalid drive letter.")
        sys.exit(1)

    drive_letter += ":"

    # Process each line from bads.txt
    for line_no, line in enumerate(lines, start=1):
        # Skip empty lines and comments
        line = line.split(";")[0].strip()
        if not line:
            continue

        try:
            # Parse the sector value and multiplier
            sector_value, multiplier = map(int, line.split(","))
            start_position = sector_value
            end_position = sector_value + multiplier

            # Construct the command
            command = f'NTFSMARKBAD {drive_letter} {start_position} {end_position}'
            print(f"[{line_no}] Running: {command}")

            # Run the command as administrator
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            # Show the output
            if result.returncode != 0:
                print(f"Error processing line {line_no}: {result.stderr.strip()}")
            else:
                print(f"Line {line_no} completed: {result.stdout.strip()}")

        except ValueError:
            print(f"Error parsing line {line_no}: {line}")

    print("\nAll lines processed. Check the output for any errors.")
    print("Process completed successfully. Congratulations!")

if __name__ == "__main__":
    main()
