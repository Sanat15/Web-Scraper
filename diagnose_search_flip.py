"""
diagnose_search_flip.py

Runs consecutive Goodreads searches through ONE persistent GoodreadsScraper
session -- same session/cookies/throttle as pipeline.py uses across a real
batch -- and prints full detail for every single request. Unlike
check_search_block.py (which only ever tests one ISBN in isolation), this
lets us actually watch the point where success flips to failure, and what
the response looks like right at that moment, instead of guessing.

Usage:
    python diagnose_search_flip.py test_50_isbns.csv 20

    (isbns_csv_path, how_many_to_test -- defaults to test_50_isbns.csv, 15)
"""

import csv
import sys
from urllib.parse import quote

from scrapers.goodreads import GoodreadsScraper, SEARCH_URL

BLOCK_MARKERS = [
    "captcha", "unusual traffic", "verify you are a human", "verify you're human",
    "access to this page has been denied", "are you a robot", "automated access",
    "please enable javascript and cookies", "/errors/", "blocked",
]


def main(csv_path: str, limit: int) -> None:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        # skip header row if it looks non-numeric
        if rows and not rows[0][0].strip().isdigit():
            rows = rows[1:]
        isbns = [row[0].strip() for row in rows[:limit]]

    print(f"Testing {len(isbns)} ISBNs through one persistent session, "
          f"same as pipeline.py would.\n")

    saved_count = 0
    with GoodreadsScraper() as scraper:
        for i, isbn in enumerate(isbns, start=1):
            url = SEARCH_URL.format(query=quote(isbn))
            resp = scraper._get(url)

            if resp is None:
                print(f"[{i:02}] {isbn}: _get() returned None "
                      f"(network failure or repeated 429/503 after retries)")
                continue

            redirected = "/book/show/" in resp.url
            markers = [m for m in BLOCK_MARKERS if m in resp.text.lower()]

            status_line = (
                f"[{i:02}] {isbn}: status={resp.status_code} "
                f"redirected_to_book={redirected} markers={markers} "
                f"body_len={len(resp.text)}"
            )
            print(status_line)

            if not redirected and saved_count < 5:
                fname = f"flip_point_{i:02}_{isbn}.html"
                with open(fname, "w", encoding="utf-8") as out:
                    out.write(resp.text)
                snippet = resp.text[:200].replace("\n", " ").strip()
                print(f"        -> saved body to {fname}")
                print(f"        -> first 200 chars: {snippet!r}")
                saved_count += 1

    print("\nDone. If requests flipped from redirected=True to "
          "redirected=False partway through, that request number is the "
          "flip point -- check its saved .html file. If markers were found "
          "anywhere, that confirms a text-detectable block. If redirected "
          "stays False with no markers from early on, that points to a "
          "soft-block (valid-looking empty page) that _looks_blocked() "
          "can't currently catch.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "test_50_isbns.csv"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    main(path, n)
