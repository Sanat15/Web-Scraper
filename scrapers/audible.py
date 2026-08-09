"""
scrapers/audible.py

Skeleton -- same interface as goodreads.py, not fleshed out.

IMPORTANT DIFFERENCE FROM THE OTHER FOUR: Audible product pages are
partially public (title, author, blurb, cover are usually visible logged
out), but reviews and some catalog details are commonly gated behind an
Amazon/Audible account login. If Task 4's "25 reviews per source" turns
out to be genuinely required for Audible, you likely need an authenticated
Selenium session (real login, cookies persisted across the run) rather
than plain requests -- worth confirming early since it changes this
file's shape more than the others. Flag this to your professor if it
becomes a blocker; scraping behind a personal login for a class
assignment is also worth a quick sanity check with them.

Also: audiobooks don't have a print "Publisher" or "Origin/Country of
publication" in the usual sense -- expect to record the audiobook
publisher/studio instead, or leave the field null with a note, per
"handle missing data gracefully".
"""

from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapeResult

SEARCH_URL = "https://www.audible.com/search?keywords={query}"


class AudibleScraper(BaseScraper):
    source_name = "audible"

    def scrape_book(self, isbn13: str) -> ScrapeResult:
        result = ScrapeResult(isbn13=isbn13, source=self.source_name)

        book_url = self._find_book_url(isbn13)
        if not book_url:
            result.errors["metadata"] = "no Audible listing found for this ISBN-13 (note: Audible catalogs by ASIN, not ISBN -- not every print ISBN has an audiobook edition at all)"
            return result

        resp = self._get(book_url)
        if resp is None:
            result.errors["metadata"] = "product page request failed"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # TODO: title, author(s)/narrator, publisher (audiobook studio),
        # blurb, cover -- inspect a live Audible product page (logged out
        # first) and fill these in following the goodreads.py pattern.
        # TODO: reviews -- see login-wall note in the module docstring above
        # before spending time on selectors here.
        result.errors["metadata"] = "parsing not implemented -- inspect a live page first"

        return result

    def _find_book_url(self, isbn13: str) -> str | None:
        resp = self._get(SEARCH_URL.format(query=quote(isbn13)))
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # TODO VERIFY: adjust selector to match real search-result markup.
        link = soup.select_one("li.productListItem a.bc-link")
        if link and link.get("href"):
            href = link["href"]
            return href if href.startswith("http") else "https://www.audible.com" + href
        return None
