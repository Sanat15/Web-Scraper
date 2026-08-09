"""
scrapers/kobo.py

Skeleton -- same interface as goodreads.py, not fleshed out. Kobo's store
pages are generally server-rendered (less JS-dependent than Goodreads'
review widget or Amazon's listings), so plain requests/BeautifulSoup is
likely enough here without touching self.driver at all -- worth trying
before reaching for Selenium.
"""

from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapeResult

SEARCH_URL = "https://www.kobo.com/search?query={query}"


class KoboScraper(BaseScraper):
    source_name = "kobo"

    def scrape_book(self, isbn13: str) -> ScrapeResult:
        result = ScrapeResult(isbn13=isbn13, source=self.source_name)

        book_url = self._find_book_url(isbn13)
        if not book_url:
            result.errors["metadata"] = "no Kobo listing found for this ISBN-13"
            return result

        resp = self._get(book_url)
        if resp is None:
            result.errors["metadata"] = "book page request failed"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # TODO: title, author(s), publisher, publication date, language,
        # blurb, cover, and reviews all need real selectors -- inspect a
        # live Kobo book page and fill these in following the same pattern
        # as goodreads.py.
        result.errors["metadata"] = "parsing not implemented -- inspect a live page first"

        return result

    def _find_book_url(self, isbn13: str) -> str | None:
        resp = self._get(SEARCH_URL.format(query=quote(isbn13)))
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # TODO VERIFY: adjust selector to match real search-result markup.
        link = soup.select_one("a.item-link")
        if link and link.get("href"):
            href = link["href"]
            return href if href.startswith("http") else "https://www.kobo.com" + href
        return None
