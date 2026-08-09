"""
scrapers/amazon.py

Skeleton -- same interface as goodreads.py, not fleshed out. Amazon
specifically is worth extra caution: it has the most aggressive anti-bot
detection of the five sources (CAPTCHAs, IP-based rate limiting well below
what a naive "1.5s delay" budget assumes), so treat failures here as
expected, not as bugs in your code. Consider testing this one LAST, after
your manifest/retry/checkpoint infrastructure is already proven on the
friendlier sources, so a bad Amazon session doesn't burn your test time.

Amazon book pages are publicly viewable without login (unlike Audible).
"""

from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapeResult

SEARCH_URL = "https://www.amazon.com/s?k={query}&i=stripbooks"


class AmazonScraper(BaseScraper):
    source_name = "amazon"

    def scrape_book(self, isbn13: str) -> ScrapeResult:
        result = ScrapeResult(isbn13=isbn13, source=self.source_name)

        product_url = self._find_product_url(isbn13)
        if not product_url:
            result.errors["metadata"] = "no Amazon listing found for this ISBN-13"
            return result

        resp = self._get(product_url)
        if resp is None:
            result.errors["metadata"] = "product page request failed (possibly bot-blocked -- check for a CAPTCHA page)"
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # TODO: title -> #productTitle
        # TODO: authors -> .author a / #bylineInfo a
        # TODO: publisher + publication date + language -> usually inside the
        #       "Product details" / "#detailBullets_feature_div" list, as
        #       label: value pairs -- parse that list rather than guessing
        #       fixed positions, labels move depending on category.
        # TODO: blurb -> #bookDescription_feature_div
        # TODO: cover -> #imgBlkFront or #landingImage (src or data-a-dynamic-image)
        # TODO: reviews -> product review pages are paginated and often
        #       require the "see all reviews" link; 25+ reviews will need
        #       several page fetches through self._get() (delay applies
        #       automatically), or Selenium if content is JS-gated.
        result.errors["metadata"] = "parsing not implemented -- see TODOs above"

        return result

    def _find_product_url(self, isbn13: str) -> str | None:
        resp = self._get(SEARCH_URL.format(query=quote(isbn13)))
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        # TODO VERIFY: search results are div[data-component-type="s-search-result"]
        # with the product link inside an h2 > a.
        link = soup.select_one('div[data-component-type="s-search-result"] h2 a')
        if link and link.get("href"):
            href = link["href"]
            return href if href.startswith("http") else "https://www.amazon.com" + href
        return None
