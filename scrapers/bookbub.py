"""
scrapers/bookbub.py

Skeleton -- same interface as goodreads.py, not fleshed out. BookBub is
less commonly scraped than the other four, so treat every selector below
as a starting guess, more than the others.
"""

from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapeResult

SEARCH_URL = "https://www.bookbub.com/search?text={query}"


class BookBubScraper(BaseScraper):
    source_name = "bookbub"

    def scrape_book(self, isbn13: str) -> ScrapeResult:
        result = ScrapeResult(isbn13=isbn13, source=self.source_name)

        book_url = self._find_book_url(isbn13)
        if not book_url:
            result.errors["metadata"] = "no BookBub listing found for this ISBN-13"
            return result

        resp = self._get(book_url)
        if resp is None:
            result.errors["metadata"] = "book page request failed"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # TODO: title, author(s), publisher, blurb, cover, genres/categories,
        # and reviews all need real selectors -- inspect a live BookBub book
        # page and fill these in following the same pattern as goodreads.py
        # (one small _parse_* method per field group, wrapped in try/except,
        # missing fields logged to result.errors rather than crashing).
        result.errors["metadata"] = "parsing not implemented -- inspect a live page first"

        return result

    def _find_book_url(self, isbn13: str) -> str | None:
        resp = self._get(SEARCH_URL.format(query=quote(isbn13)))
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # TODO VERIFY: adjust selector to match real search-result markup.
        link = soup.select_one("a[href*='/books/']")
        if link and link.get("href"):
            href = link["href"]
            return href if href.startswith("http") else "https://www.bookbub.com" + href
        return None
