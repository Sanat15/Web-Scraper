"""
make_test_subset.py

Slices the first N rows off data_cleaned_isbns.csv into a small test file,
so you can run the pipeline against 50 books instead of 9,991 while you're
still verifying selectors / checking the plumbing works.

Usage:
    python make_test_subset.py            # first 50 (default)
    python make_test_subset.py 20         # first 20
"""

import csv
import sys

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
SRC = "data_cleaned_isbns.csv"
OUT = f"test_{N}_isbns.csv"

with open(SRC, newline="", encoding="utf-8") as f_in:
    reader = csv.reader(f_in)
    header = next(reader)
    rows = [row for _, row in zip(range(N), reader)]

with open(OUT, "w", newline="", encoding="utf-8") as f_out:
    writer = csv.writer(f_out)
    writer.writerow(header)
    writer.writerows(rows)

print(f"Wrote {len(rows)} ISBNs to {OUT}")
