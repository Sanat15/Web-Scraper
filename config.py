"""
config.py

Single source of truth for paths, source names, and timing. Every other
module imports from here instead of hardcoding strings, so if the professor
confirms a different folder layout later, this is the only file to touch.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# Confirmed with the professor: all five sources are required.
SOURCES = ["goodreads", "amazon", "bookbub", "kobo", "audible"]

# ---------------------------------------------------------------------------
# Folder structure (Section 4 of the assignment, confirmed against the PDF)
# ---------------------------------------------------------------------------
DATA_ROOT = Path("data")

FOLDERS = {
    "metadata": DATA_ROOT / "book_metadata",
    "coverpage": DATA_ROOT / "book_coverpage",
    "blurb": DATA_ROOT / "book_blurb",
    "reviews": DATA_ROOT / "book_reviews",
    # No separate genres/ folder -- confirmed with the professor that Task 5's
    # written wording is superseded; genre lives only inside the "Genre"
    # field of each book_metadata/<source>_metadata.json entry.
}

MANIFEST_DB = Path("progress_manifest.sqlite3")

# ---------------------------------------------------------------------------
# Scrape behaviour
# ---------------------------------------------------------------------------
REQUEST_DELAY_SECONDS = 2.0   # base delay; base.py adds jitter on top (see _throttle)
MIN_REVIEWS_PER_BOOK = 25     # Task 4: "at least 25 reviews per source"
CHECKPOINT_EVERY_N_BOOKS = 50  # Maam's batch cadence -- used for zip/commit checkpoints, not as a loop boundary

# ---------------------------------------------------------------------------
# Metadata field names -- exact keys, matching Task 1 and your own spec
# ---------------------------------------------------------------------------
METADATA_FIELDS = [
    "ISBN-13",
    "Author(s)",
    "Title",
    "Publisher",
    "Origin / Country of publication",
    "Date of publication",
    "Language",
    "Genre",
]
