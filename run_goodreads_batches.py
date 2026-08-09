"""
run_goodreads_batches.py

Runs the full ISBN list through pipeline.py in chunks (default 50) for a
single source (default goodreads), watching the live output for two
specific signals:

  - "no Goodreads book page found for this ISBN-13"  (real failure OR
    the WAF challenge persisting even after the Selenium fallback)
  - "WAF challenge passed via Selenium"                (fallback firing)

A couple of misses per batch is normal (books that genuinely aren't on
Goodreads). But if a batch's "not found" rate crosses --fail-threshold
(default 20%), that's the WAF signature again -- the runner STOPS there
instead of continuing to burn requests against what's probably still a
block, and tells you how to resume once it's sorted out.

After each batch that passes the threshold check, this batch's new files
(matched by ISBN prefix across the four data/ subfolders) are zipped and
uploaded to a GitHub Release as an asset -- NOT committed to git, per the
"raw data stays out of the repo" plan.

Usage:
    python run_goodreads_batches.py
    python run_goodreads_batches.py --batch-size 50 --fail-threshold 0.2
    python run_goodreads_batches.py --start-batch 4          (resume)
    python run_goodreads_batches.py --no-github               (zip only, skip upload)

Assumes:
    - data_cleaned_isbns.csv exists (the full ISBN list) in the current dir.
    - Saved files are named starting with the ISBN, e.g.
      data/book_metadata/<isbn>.json -- VERIFY this against your actual
      data/ folder before relying on the zip step; adjust the glob in
      zip_batch_data() if your naming differs.
    - `gh` (GitHub CLI) is installed and authenticated, if not using --no-github.
"""

import argparse
import csv
import os
import subprocess
import sys
import zipfile
from pathlib import Path

DATA_SUBFOLDERS = ["book_metadata", "book_coverpage", "book_blurb", "book_reviews"]
NOT_FOUND_MSG = "no Goodreads book page found for this ISBN-13"
WAF_PASS_MSG = "WAF challenge passed via Selenium"


def read_isbns(csv_path: str) -> list[str]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if rows and not rows[0][0].strip().isdigit():
        rows = rows[1:]  # skip header
    return [row[0].strip() for row in rows if row and row[0].strip()]


def chunked(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def write_batch_csv(isbns: list[str], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Isbn-13"])
        for isbn in isbns:
            w.writerow([isbn])


def run_pipeline(batch_csv: str, source: str) -> tuple[int, int, int]:
    """Runs pipeline.py as a subprocess, mirrors its output live to the
    console (so it looks/feels exactly like running it directly), and
    counts the two signal lines as they stream past."""
    cmd = [sys.executable, "pipeline.py", "--batch", batch_csv, "--sources", source]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=env,
    )
    not_found_count = 0
    waf_pass_count = 0
    for line in proc.stdout:
        print(line, end="")
        if NOT_FOUND_MSG in line:
            not_found_count += 1
        if WAF_PASS_MSG in line:
            waf_pass_count += 1
    proc.wait()
    return proc.returncode, not_found_count, waf_pass_count


def zip_batch_data(isbns: list[str], out_zip_path: str) -> int:
    """Bundles this batch's files (matched by ISBN-prefix filename) from
    each data/ subfolder into one zip. Returns how many files were found,
    so you can sanity-check nothing was silently skipped."""
    file_count = 0
    with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in DATA_SUBFOLDERS:
            folder = Path("data") / sub
            if not folder.exists():
                continue
            for isbn in isbns:
                for match in folder.glob(f"{isbn}*"):
                    zf.write(match, arcname=f"{sub}/{match.name}")
                    file_count += 1
    return file_count


def upload_to_github(zip_path: str, release_tag: str) -> None:
    exists = subprocess.run(
        ["gh", "release", "view", release_tag], capture_output=True
    ).returncode == 0
    if not exists:
        subprocess.run(
            ["gh", "release", "create", release_tag,
             "--title", release_tag, "--notes", "Scraped Goodreads data, batched"],
            check=True,
        )
    subprocess.run(["gh", "release", "upload", release_tag, zip_path, "--clobber"], check=True)
    print(f"  -> uploaded {zip_path} to GitHub release '{release_tag}'")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-csv", default="data_cleaned_isbns.csv")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--source", default="goodreads")
    ap.add_argument("--fail-threshold", type=float, default=0.2,
                     help="Fraction of a batch allowed to fail with "
                          "'no book page found' before stopping (default 0.2 = 20%%)")
    ap.add_argument("--release-tag", default="goodreads-data")
    ap.add_argument("--no-github", action="store_true",
                     help="Zip each batch locally but skip the GitHub upload step")
    ap.add_argument("--start-batch", type=int, default=1,
                     help="1-indexed batch number to start/resume from")
    args = ap.parse_args()

    all_isbns = read_isbns(args.source_csv)
    batches = list(chunked(all_isbns, args.batch_size))
    print(f"Loaded {len(all_isbns)} ISBNs -> {len(batches)} batches of up to {args.batch_size}\n")

    os.makedirs("batch_zips", exist_ok=True)

    for i, batch_isbns in enumerate(batches, start=1):
        if i < args.start_batch:
            continue

        print(f"\n{'=' * 70}\nBATCH {i}/{len(batches)}  ({len(batch_isbns)} books)\n{'=' * 70}")
        batch_csv = f"_batch_{i:04}.csv"
        write_batch_csv(batch_isbns, batch_csv)

        returncode, not_found, waf_passes = run_pipeline(batch_csv, args.source)

        if waf_passes:
            print(f"\n  -> WAF challenge fired and was passed via Selenium "
                  f"{waf_passes} time(s) this batch.")

        fail_ratio = not_found / len(batch_isbns)
        print(f"  -> batch {i}: {not_found}/{len(batch_isbns)} "
              f"'not found' ({fail_ratio:.0%})")

        if fail_ratio > args.fail_threshold:
            print(f"\n*** STOPPING: batch {i} hit a {fail_ratio:.0%} 'not found' rate, "
                  f"above the {args.fail_threshold:.0%} threshold. ***")
            print("This usually means the WAF challenge is persisting even after the "
                  "Selenium fallback (check above for whether a WAF-pass was attempted "
                  "and still failed), or something upstream changed. Diagnose with "
                  "diagnose_search_flip.py before continuing.")
            print(f"Once resolved, resume with: "
                  f"python run_goodreads_batches.py --start-batch {i}")
            print("(Books already marked done in this batch are skipped automatically "
                  "either way, via the manifest's resumability.)")
            sys.exit(1)

        zip_path = os.path.join("batch_zips", f"goodreads_batch_{i:04}.zip")
        file_count = zip_batch_data(batch_isbns, zip_path)
        print(f"  -> zipped {file_count} files to {zip_path}")

        if args.no_github:
            print("  -> --no-github set, skipping upload")
        else:
            upload_to_github(zip_path, args.release_tag)

    print("\nAll batches complete.")


if __name__ == "__main__":
    main()
