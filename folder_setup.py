"""
folder_setup.py

Creates the folder structure mandated in Section 4 of the assignment.
Safe to call every run -- mkdir(parents=True, exist_ok=True) never
touches files that already exist, so re-running never wipes progress.
"""

from config import DATA_ROOT, FOLDERS


def setup_folders(verbose: bool = True) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for name, path in FOLDERS.items():
        path.mkdir(parents=True, exist_ok=True)
        if verbose:
            print(f"  ok  {path}/")


if __name__ == "__main__":
    print("Creating folder structure...")
    setup_folders()
    print("Done.")
