"""
checkpoint.py

Implements the checkpoint strategy from the earlier architecture
discussion: don't commit thousands of loose review/cover files straight
into git history. Instead, at each checkpoint:

  1. Commit + push the lean stuff directly (code, the 5 metadata JSON
     files, progress_manifest.sqlite3) -- small, diffable, belongs in git.
  2. Zip everything else (book_coverpage/, book_blurb/, book_reviews/,
     genres/) into one dated archive and leave it for you to attach to a
     GitHub Release or push to Drive -- NOT committed as loose files.

Run standalone any time:  python checkpoint.py
Or import run_checkpoint() and call it from your own loop every N books.

Requires: git initialized in this directory already (git init, remote
added) -- this script commits and pushes to whatever the current branch's
upstream is, it does not set one up for you.
"""

import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_ROOT, FOLDERS, MANIFEST_DB

LEAN_PATHS = [FOLDERS["metadata"], MANIFEST_DB]  # small + text -- fine to commit directly
BULK_FOLDERS = [FOLDERS["coverpage"], FOLDERS["blurb"], FOLDERS["reviews"]]


def zip_bulk_data(archive_dir: Path = Path("archives")) -> Path:
    archive_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"book_data_{stamp}.zip"

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in BULK_FOLDERS:
            if not folder.exists():
                continue
            for file_path in folder.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(DATA_ROOT.parent))

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"Zipped bulk data -> {archive_path} ({size_mb:.1f} MB)")
    if size_mb > 1900:  # GitHub Releases cap a single asset around 2GB
        print("  WARNING: approaching GitHub's ~2GB release-asset limit -- consider splitting or checkpointing more often.")
    return archive_path


def git_commit_and_push(message: str) -> None:
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True)

    paths_to_add = [str(p) for p in LEAN_PATHS if p.exists()]
    if not paths_to_add:
        print("Nothing lean to commit yet.")
        return

    add_result = run(["git", "add", *paths_to_add])
    if add_result.returncode != 0:
        print(f"git add failed: {add_result.stderr}", file=sys.stderr)
        return

    commit_result = run(["git", "commit", "-m", message])
    if commit_result.returncode != 0:
        # Most common cause: nothing changed since last checkpoint -- not an error.
        print(f"git commit: {commit_result.stdout.strip() or commit_result.stderr.strip()}")
        return

    push_result = run(["git", "push"])
    if push_result.returncode != 0:
        print(f"git push failed (committed locally, push it manually): {push_result.stderr}", file=sys.stderr)
    else:
        print("Pushed checkpoint to remote.")


def run_checkpoint(book_count: int = None) -> None:
    label = f" after {book_count} books" if book_count else ""
    print(f"\n--- Checkpoint{label} ---")
    zip_bulk_data()
    git_commit_and_push(f"checkpoint{label}: metadata + manifest update")


if __name__ == "__main__":
    run_checkpoint()
