"""
debug_page.py

Fetches a URL exactly the way the scraper does (same session, headers,
delay) and saves the raw HTML to disk, plus runs a few quick text checks.
This answers the one question that matters most right now: is content
actually present in what requests/BeautifulSoup can see, or does it only
show up after JavaScript runs in a real browser (in which case selectors
alone won't ever find it, no matter how you tweak them -- you'd need
self.driver / Selenium instead)?

Usage:
    python debug_page.py https://www.goodreads.com/book/show/<id>

Then open debug_page.html in a text editor (or your browser's "View Page
Source", Ctrl+U, NOT the regular inspect-element view) and Ctrl+F for
things you know should be there -- a reviewer name you saw on the
rendered page, "Published", "ISBN", etc.
"""

import sys

from scrapers.goodreads import GoodreadsScraper

if len(sys.argv) < 2:
    print("Usage: python debug_page.py <goodreads book URL>")
    sys.exit(1)

url = sys.argv[1]

with GoodreadsScraper() as scraper:
    resp = scraper._get(url)
    if resp is None:
        print("Request failed -- see the WARNING above for why.")
        sys.exit(1)

    out_path = "debug_page.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(resp.text)

    print(f"Final URL after redirects: {resp.url}")
    print(f"Saved {len(resp.text):,} characters to {out_path}\n")

    # Edit these to match whatever you can see on the rendered page for
    # this specific book -- a reviewer name, a distinctive review phrase,
    # the publisher name, etc.
    checks = {
        "'ISBN' text": "ISBN" in resp.text,
        "'Published' text": "Published" in resp.text,
        "'data-testid=\"review' attribute": 'data-testid="review' in resp.text,
        "'data-testid=\"publicationInfo\"' attribute": 'data-testid="publicationInfo"' in resp.text,
    }
    print("Quick checks against the raw HTML:")
    for label, found in checks.items():
        print(f"  contains {label}: {found}")
    print("\nIf 'review' text/attributes are False here but you can see reviews")
    print("in your normal browser, they're JS-injected -- selectors on this raw")
    print("HTML will never find them, and _parse_reviews needs self.driver instead.")
