from scrapers.goodreads import GoodreadsScraper
from scrapers.amazon import AmazonScraper
from scrapers.bookbub import BookBubScraper
from scrapers.kobo import KoboScraper
from scrapers.audible import AudibleScraper

SCRAPER_REGISTRY = {
    "goodreads": GoodreadsScraper,
    "amazon": AmazonScraper,
    "bookbub": BookBubScraper,
    "kobo": KoboScraper,
    "audible": AudibleScraper,
}
