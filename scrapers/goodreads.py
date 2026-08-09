"""
scrapers/goodreads.py

Rewritten around __NEXT_DATA__ instead of CSS selectors, after your
debug_page.py + verify_next_data.py findings. Goodreads is a Next.js app
using an Apollo GraphQL client -- the ENTIRE page's data is embedded as
JSON in <script id="__NEXT_DATA__">, which React reads to hydrate the
page. That JSON is far more complete and stable than guessing CSS
classes: it's what gave us the real publisher, all 30 reviews, and a
reliable ISBN to verify against, none of which the old selector-based
version could see.

Structure (confirmed against a real page, ISBN 9780747531852 / Bullitt):

    __NEXT_DATA__
      .props.pageProps.apolloState        <- normalized Apollo cache, {ref: object}
        ROOT_QUERY
          .getBookByLegacyId({...})       <- {"__ref": "Book:kca://book/..."}
          .getReviews.edges[]             <- each {"node": {"__ref": "Review:..."}}
        "Book:kca://book/...":
          title, description,
          description({"stripped":true})  <- plain-text version, no HTML tags
          imageUrl
          primaryContributorEdge.node.__ref      -> "Contributor:..."
          secondaryContributorEdges[].node.__ref -> "Contributor:..."
          bookGenres[].genre.name
          details: { isbn13, publisher, publicationTime (ms since epoch),
                      language.name, asin, format, numPages }
          work.__ref -> "Work:..." (stats.ratingsCountDist etc. -- see note below)
        "Contributor:...": { name, ... }
        "Review:...": { text (HTML), rating (1-5), likeCount, creator.__ref -> "User:..." }
        "User:...": { name, ... }

Cache keys are content-addressed per book, so they differ across ISBNs --
always resolve via ROOT_QUERY's getBookByLegacyId/getReviews entries
(matched by key PREFIX, not the full parameterized key) rather than
hardcoding any specific ref string.

publicationTime is Windows-unsafe to convert with datetime.fromtimestamp()
-- older editions can predate 1970 (the original work here does: 1963),
and Windows' C runtime raises on negative timestamps. Converted manually
via timedelta instead; see _ms_to_date_string.

Reviews come back from getReviews.edges already sorted by likeCount
descending (confirmed against your screenshots: 44, 7, 3, 3, 2...) -- your
"top 3 by likes" instinct was right about the ordering, we're just taking
all ~30 rather than only the top 3, since the assignment wants >=25.

Bonus, not used for any required file: work.stats has averageRating,
ratingsCount, and ratingsCountDist (a 5-element [1-star..5-star] count
list -- confirmed it matches the breakdown in your screenshot exactly).
That's the "overall rating + star breakdown" data from your idea, if you
want to capture it as extra/supplementary info later -- ask your
professor first, since it's not part of the agreed metadata schema.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScrapeResult

SEARCH_URL = "https://www.goodreads.com/search?q={query}"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


class GoodreadsScraper(BaseScraper):
    source_name = "goodreads"

    def scrape_book(self, isbn13: str) -> ScrapeResult:
        result = ScrapeResult(isbn13=isbn13, source=self.source_name)

        book_url = self._find_book_url(isbn13)
        if not book_url:
            result.errors["metadata"] = "no Goodreads book page found for this ISBN-13"
            return result

        resp = self._get(book_url)
        if resp is None:
            result.errors["metadata"] = "book page request failed"
            return result

        next_data = self._extract_next_data(resp.text)
        if next_data is None:
            result.errors["metadata"] = (
                "could not find/parse __NEXT_DATA__ on this page -- Goodreads may have "
                "changed its page structure; run debug_page.py on this URL to check"
            )
            return result

        try:
            apollo = next_data["props"]["pageProps"]["apolloState"]
            root = apollo["ROOT_QUERY"]
        except KeyError as e:
            result.errors["metadata"] = f"__NEXT_DATA__ structure changed (missing {e})"
            return result

        book = self._resolve_book(apollo, root)
        if book is None:
            result.errors["metadata"] = "no Book object found in the page's data"
            return result

        # SAFETY CHECK: verify the book we landed on actually matches the ISBN
        # we searched for -- see module docstring / the mismatched-edition case
        # you found earlier. Now checking the structured field instead of
        # regexing visible text, so it's exact rather than best-effort.
        page_isbn = (book.get("details") or {}).get("isbn13")
        if page_isbn and page_isbn != isbn13:
            result.errors["metadata"] = (
                f"landed on a DIFFERENT book (page's ISBN-13 is {page_isbn}, "
                f"searched for {isbn13}) -- likely a mismatched search result; "
                f"not saving this data"
            )
            print(f"WARNING [{self.source_name}] {isbn13}: {result.errors['metadata']}")
            return result

        self._parse_metadata(apollo, book, isbn13, result)
        self._parse_blurb(book, result)
        self._parse_cover_images(book, result)
        self._parse_reviews(apollo, root, book, result)

        return result

    # -- Step 1: ISBN -> book URL ------------------------------------------------

    def _find_book_url(self, isbn13: str) -> str | None:
        resp = self._get(SEARCH_URL.format(query=quote(isbn13)))
        if resp is None:
            return None
        if self._looks_blocked(resp):
            print(f"WARNING [{self.source_name}] {isbn13}: response looks like a "
                  f"bot-check/rate-limit page, not real search results -- this is "
                  f"NOT a 'book not found' case, back off and retry later")
            return None
        if "/book/show/" in resp.url:
            return resp.url
        # Fell back to a results LIST page instead of redirecting -- grab
        # the first result link. (This is the fuzzy-match path that
        # produced the Aero Armor Series mismatch -- the ISBN check above
        # is what catches it now.)
        soup = BeautifulSoup(resp.text, "html.parser")
        link = soup.select_one("a.bookTitle")
        if link and link.get("href"):
            return "https://www.goodreads.com" + link["href"]
        return None

    # -- Step 2: pull __NEXT_DATA__ and resolve the Book object -------------------

    def _extract_next_data(self, html: str) -> dict | None:
        m = NEXT_DATA_RE.search(html)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None

    def _resolve_ref(self, apollo: dict, ref_obj: dict | None) -> dict | None:
        """ref_obj looks like {'__ref': 'Contributor:kca://...'} -- follow it
        into the normalized cache. Returns None if absent/dangling."""
        if not ref_obj or "__ref" not in ref_obj:
            return None
        return apollo.get(ref_obj["__ref"])

    def _resolve_book(self, apollo: dict, root: dict) -> dict | None:
        # The key is parameterized with the specific legacyId, e.g.
        # 'getBookByLegacyId({"legacyId":"1475845"})' -- match by prefix
        # since we don't know the id in advance.
        key = next((k for k in root if k.startswith("getBookByLegacyId(")), None)
        if key is None:
            return None
        return self._resolve_ref(apollo, root[key])

    # -- Step 3: metadata ----------------------------------------------------------

    def _ms_to_date_string(self, ms) -> str | None:
        """Windows-safe: datetime.fromtimestamp() raises on negative
        timestamps (pre-1970 dates) on Windows -- real for this dataset,
        e.g. this book's ORIGINAL 1963 publication. Manual timedelta
        arithmetic avoids the platform C-library call entirely."""
        if ms is None:
            return None
        try:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)
            return dt.strftime("%Y-%m-%d")
        except OverflowError:
            return None

    def _parse_metadata(self, apollo: dict, book: dict, isbn13: str, result: ScrapeResult) -> None:
        try:
            title = book.get("title")

            authors = []
            primary = self._resolve_ref(apollo, (book.get("primaryContributorEdge") or {}).get("node"))
            if primary and primary.get("name"):
                authors.append(primary["name"])
            for edge in book.get("secondaryContributorEdges", []) or []:
                obj = self._resolve_ref(apollo, edge.get("node"))
                if obj and obj.get("name"):
                    authors.append(obj["name"])

            details = book.get("details") or {}
            publisher = details.get("publisher")
            language = (details.get("language") or {}).get("name")
            # Edition-specific date (matches this ISBN), not the original
            # work's first-published date -- see module docstring.
            pub_date = self._ms_to_date_string(details.get("publicationTime"))

            genres = [
                (bg.get("genre") or {}).get("name")
                for bg in (book.get("bookGenres") or [])
                if (bg.get("genre") or {}).get("name")
            ]
            result.genres = genres  # kept on the result object; not written to a separate file

            missing = [k for k, v in {
                "Title": title, "Author(s)": authors, "Publisher": publisher,
                "Date of publication": pub_date, "Language": language,
            }.items() if not v]
            if missing:
                # Legitimate on Goodreads for many books (confirmed by you already
                # for Publisher/Language/Genre on several titles) -- not necessarily a bug.
                result.errors["metadata"] = f"fields not present in Goodreads' data: {', '.join(missing)}"

            result.metadata = {
                "ISBN-13": isbn13,
                "Author(s)": ", ".join(authors) if authors else None,
                "Title": title,
                "Publisher": publisher,
                # Not present in Goodreads' data model -- see README.
                "Origin / Country of publication": None,
                "Date of publication": pub_date,
                "Language": language,
                "Genre": ", ".join(genres) if genres else None,
            }
        except Exception as e:
            result.errors["metadata"] = f"parse error: {e}"
            print(f"WARNING [{self.source_name}]: metadata parse failed for {isbn13}: {e}")

    # -- Step 4: blurb ---------------------------------------------------------------

    @staticmethod
    def _strip_html(text: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _parse_blurb(self, book: dict, result: ScrapeResult) -> None:
        try:
            # The stripped variant is already plain text (no tags); fall back
            # to manually stripping the HTML one if it's ever absent.
            desc = book.get('description({"stripped":true})') or book.get("description")
            result.blurb = self._strip_html(desc) if desc else None
            if not result.blurb:
                result.errors["blurb"] = "no description in Goodreads' data for this book"
        except Exception as e:
            result.errors["blurb"] = f"parse error: {e}"

    # -- Step 5: cover image ----------------------------------------------------------

    def _parse_cover_images(self, book: dict, result: ScrapeResult) -> None:
        try:
            img_url = book.get("imageUrl")
            if img_url:
                img_bytes = self._download_image(img_url)
                if img_bytes:
                    result.cover_images.append(img_bytes)
            if not result.cover_images:
                result.errors["coverpage"] = "no imageUrl in Goodreads' data for this book"
        except Exception as e:
            result.errors["coverpage"] = f"parse error: {e}"

    # -- Step 6: reviews ------------------------------------------------------------

    def _parse_reviews(self, apollo: dict, root: dict, book: dict, result: ScrapeResult) -> None:
        try:
            key = next((k for k in root if k.startswith("getReviews")), None)
            found_via_query = False
            if key is not None:
                for edge in (root[key].get("edges") or []):
                    review = self._resolve_ref(apollo, edge.get("node"))
                    if not review or not review.get("text"):
                        continue
                    text = self._strip_html(review["text"])
                    rating = review.get("rating")
                    header = f"Rating: {rating}/5\n\n" if rating else ""
                    result.reviews.append(header + text)
                found_via_query = True

            if not result.reviews:
                # Cross-check against Goodreads' OWN review count (work.stats.
                # textReviewsCount) to tell "book genuinely has 0 reviews"
                # (expected, not a bug -- common for older/obscure editions)
                # apart from "reviews exist but we failed to extract them"
                # (a real gap worth investigating with debug_page.py).
                work = self._resolve_ref(apollo, book.get("work"))
                total = ((work or {}).get("stats") or {}).get("textReviewsCount")
                if total == 0:
                    result.errors["reviews"] = "confirmed 0 reviews for this book on Goodreads (work.stats.textReviewsCount == 0) -- not a bug"
                elif total:
                    result.errors["reviews"] = (
                        f"Goodreads shows {total} reviews exist (work.stats.textReviewsCount) but "
                        f"{'the getReviews query was missing from this page' if not found_via_query else 'edges came back empty'} "
                        f"-- worth investigating with debug_page.py on this book specifically"
                    )
                else:
                    result.errors["reviews"] = "no getReviews entry AND no work.stats.textReviewsCount to cross-check against"
        except Exception as e:
            result.errors["reviews"] = f"parse error: {e}"
