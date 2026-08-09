"""
scrapers/base.py

Common interface every source scraper implements, plus the result type
that carries whatever a scrape managed to find. Keeping this shared means
pipeline.py never needs to know which source it's talking to -- it just
calls .scrape_book(isbn13) and handles a ScrapeResult.

Per Section 6 of the assignment: "use requests / BeautifulSoup; Selenium
is allowed if the page content is JavaScript-rendered." So the base class
gives you both a requests.Session (cheap, fast, use by default) and a lazy
Selenium driver (only spun up if a subclass actually calls self.driver) --
you don't pay Chrome's startup cost on sources that don't need it.

UPDATE: Goodreads sits behind AWS WAF, which occasionally serves a blank
JS-challenge shell (status 202, contains AwsWafIntegration/gokuProps/
token.awswaf.com) instead of real content. A real browser solves this
automatically in milliseconds; `requests` can't run JS at all and just
sees the empty shell forever -- which is NOT the same thing as "book not
found" or a classic CAPTCHA block. _looks_blocked() now recognizes this
page specifically, and _get() automatically falls back to the (already
lazy) Selenium driver ONCE to solve the challenge and harvest a valid
session cookie + matching User-Agent into self.session, so every request
after that goes back to fast plain `requests` calls -- until the token
eventually expires and the cycle repeats.
"""

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests

from config import REQUEST_DELAY_SECONDS

# Text that shows up on classic bot-check/rate-limit pages instead of real
# content (CAPTCHA interstitials, generic "unusual traffic" pages, etc).
_BLOCK_PAGE_INDICATORS = (
    "unusual traffic", "verify you are a human", "captcha", "px-captcha",
    "are you a robot", "automated queries", "access to this page has been denied",
    "request blocked",
)

# Specific to AWS WAF's JS-challenge shell page (confirmed against a real
# captured Goodreads response -- see flip_point_*.html). Distinct from the
# markers above because this page has NONE of that text; it's a blank
# shell whose only job is to run challenge.js and set a token cookie.
_WAF_CHALLENGE_INDICATORS = (
    "awswafcookiedomainlist", "awswafintegration", "gokuprops",
    "challenge-container", "token.awswaf.com",
)


@dataclass
class ScrapeResult:
    isbn13: str
    source: str

    metadata: Optional[dict] = None            # the 8 METADATA_FIELDS, or None if the book wasn't found
    cover_images: list = field(default_factory=list)   # list of raw bytes, one per edition/cover found
    blurb: Optional[str] = None
    reviews: list = field(default_factory=list)        # list of review text strings
    genres: list = field(default_factory=list)         # list of genre/tag strings

    # task_type -> human-readable reason, for anything that came back empty.
    # This is what feeds the "handle missing data gracefully" requirement --
    # print a warning, log it here, move on, never crash the whole run.
    errors: dict = field(default_factory=dict)


class BaseScraper(ABC):
    source_name: str = "base"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            # A bare User-Agent with nothing else is itself a weak bot signal --
            # real browsers always send these alongside it.
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        })
        self._driver = None  # lazily created; see .driver property
        self._last_request_time = 0.0

    @property
    def driver(self):
        """
        Lazy Selenium driver. Only import/launch Chrome the first time a
        subclass (or _pass_waf_challenge) actually touches self.driver --
        sources that never hit a JS challenge never pay this cost.
        """
        if self._driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service

            opts = Options()
            if self.headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            self._driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        return self._driver

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self._driver is not None:
            self._driver.quit()
        self.session.close()

    def _throttle(self):
        """Enforce REQUEST_DELAY_SECONDS between consecutive requests to THIS
        source, plus a bit of random jitter -- perfectly regular intervals
        are themselves a bot signal some detection systems key on."""
        elapsed = time.monotonic() - self._last_request_time
        wait = REQUEST_DELAY_SECONDS + random.uniform(0, 1.0)
        if elapsed < wait:
            time.sleep(wait - elapsed)
        self._last_request_time = time.monotonic()

    def _looks_blocked(self, resp: requests.Response) -> bool:
        """Cheap check for a bot-check/rate-limit page instead of real
        content, so a block shows up as a specific, actionable warning
        rather than a generic 'not found'. Covers both classic CAPTCHA-text
        pages AND AWS WAF's blank JS-challenge shell (status 202)."""
        if resp is None:
            return False
        snippet = resp.text[:5000].lower()
        if resp.status_code == 202 and any(m in snippet for m in _WAF_CHALLENGE_INDICATORS):
            return True
        return any(indicator in snippet for indicator in _BLOCK_PAGE_INDICATORS)

    def _pass_waf_challenge(self, url: str, wait_seconds: float = 8.0) -> bool:
        """
        Loads `url` for real in the (lazy) Selenium driver -- which executes
        challenge.js, solves AWS WAF's JS challenge, and auto-reloads once
        solved (see AwsWafIntegration.getToken().then(reload) in the
        challenge page itself). Once the driver shows real content, copies
        its cookies (including the WAF token cookie) AND its User-Agent
        into self.session, so subsequent plain `requests` calls carry a
        valid token and skip the challenge -- until it eventually expires.

        Returns True if it looks like we got past the challenge, False if
        still stuck on the shell page after wait_seconds (Selenium/Chrome
        missing, or WAF fingerprinting headless Chrome too -- either way,
        the caller falls back to treating this as a normal block).
        """
        try:
            self.driver.get(url)
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                html = self.driver.page_source.lower()
                if not any(m in html for m in _WAF_CHALLENGE_INDICATORS):
                    break
                time.sleep(0.5)
            else:
                print(f"WARNING [{self.source_name}]: still on WAF challenge page "
                      f"after {wait_seconds}s -- Selenium couldn't clear it either")
                return False

            browser_ua = self.driver.execute_script("return navigator.userAgent;")
            self.session.headers["User-Agent"] = browser_ua

            cookies = self.driver.get_cookies()
            for c in cookies:
                self.session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain"), path=c.get("path", "/"),
                )
            print(f"INFO [{self.source_name}]: WAF challenge passed via Selenium, "
                  f"{len(cookies)} cookies copied to session")
            return True
        except Exception as e:
            print(f"WARNING [{self.source_name}]: Selenium WAF-pass attempt failed: {e}")
            return False

    def _get(self, url: str, retries: int = 2, **kwargs) -> Optional[requests.Response]:
        """
        Rate-limited GET with a couple of retries on transient failures.
        Subclasses should call this (not self.session.get directly) so the
        delay, retry, and WAF-challenge-recovery logic apply everywhere
        uniformly. Returns None (never raises) on repeated failure -- the
        caller decides how to record that in ScrapeResult.errors.
        """
        last_exc = None
        waf_pass_attempted = False
        attempt = 0
        while attempt <= retries:
            self._throttle()
            try:
                resp = self.session.get(url, timeout=15, **kwargs)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (429, 503):
                    # Rate-limited/overloaded -- back off harder than usual before retrying.
                    time.sleep(REQUEST_DELAY_SECONDS * (attempt + 2))
                    attempt += 1
                    continue
                if self._looks_blocked(resp) and not waf_pass_attempted:
                    # One-time session fix, not a normal retry -- doesn't consume
                    # an attempt, since it's fixing the session, not the request.
                    waf_pass_attempted = True
                    print(f"WARNING [{self.source_name}]: hit a WAF/bot-check page for "
                          f"{url} -- attempting to pass it via Selenium and retry")
                    self._pass_waf_challenge(url)
                    continue
                # Other 4xx/5xx, or still blocked after the WAF-pass attempt:
                # not likely to resolve on further retry here.
                return resp
            except requests.RequestException as e:
                last_exc = e
                time.sleep(REQUEST_DELAY_SECONDS)
            attempt += 1
        print(f"WARNING [{self.source_name}]: GET failed after {retries + 1} attempts ({url}): {last_exc}")
        return None

    def _download_image(self, url: str) -> Optional[bytes]:
        """Shared helper: fetch a cover-image URL as raw bytes via requests (not Selenium -- binary downloads through a browser driver are unreliable)."""
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            print(f"WARNING [{self.source_name}]: cover image download failed ({url}): {e}")
            return None

    @abstractmethod
    def scrape_book(self, isbn13: str) -> ScrapeResult:
        """
        Must be implemented per source. Should never raise for "book not
        found on this source" or "field missing" -- catch those, note them
        in ScrapeResult.errors, and return what WAS found. Only let genuine
        infrastructure errors (network down, etc.) propagate.
        """
        raise NotImplementedError
