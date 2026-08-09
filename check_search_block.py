"""
check_search_block.py

Hits the Goodreads search endpoint through your actual GoodreadsScraper
session (same headers, same throttle) for one ISBN, and tells you
directly whether it's a real "not found" or a block/CAPTCHA page --
instead of eyeballing debug_page.html and guessing.

Usage:
    python check_search_block.py 9780747531852

(Uses an ISBN known to exist -- Bullitt -- by default if you don't pass one.)
"""

import sys
from urllib.parse import quote

from scrapers.goodreads import GoodreadsScraper, SEARCH_URL

BLOCK_MARKERS = [
    "captcha", "unusual traffic", "verify you are a human", "verify you're human",
    "access to this page has been denied", "are you a robot", "automated access",
    "please enable javascript and cookies", "/errors/", "blocked",
]


def main(isbn13: str) -> None:
    with GoodreadsScraper() as scraper:
        url = SEARCH_URL.format(query=quote(isbn13))
        print(f"Requesting: {url}\n")
        resp = scraper._get(url)

        if resp is None:
            print("Result: _get() returned None -- a real network failure or repeated "
                  "429/503 after retries. Check your internet connection, or this IS "
                  "confirmed rate-limiting (429/503 codes specifically).")
            return

        print(f"Status code:  {resp.status_code}")
        print(f"Final URL:    {resp.url}")
        print(f"Body length:  {len(resp.text)} chars")

        found_markers = [m for m in BLOCK_MARKERS if m in resp.text.lower()]
        redirected_to_book = "/book/show/" in resp.url

        print()
        if redirected_to_book:
            print("VERDICT: Success -- redirected straight to a book page. Not blocked.")
        elif resp.status_code in (403, 429, 503):
            print(f"VERDICT: Likely BLOCKED -- status code {resp.status_code} is a classic "
                  f"bot-detection response.")
        elif found_markers:
            print(f"VERDICT: Likely BLOCKED -- body contains block-related text: {found_markers}")
        else:
            print("VERDICT: Ambiguous -- status 200, no obvious block markers, but no "
                  "redirect either. Saving body to check_search_block_output.html so you "
                  "can look at it directly.")
            with open("check_search_block_output.html", "w", encoding="utf-8") as f:
                f.write(resp.text)


if __name__ == "__main__":
    isbn = sys.argv[1] if len(sys.argv) > 1 else "9780747531852"
    main(isbn)
