"""
result_saver.py

Turns one ScrapeResult into the actual files on disk, named exactly per
naming.py, and records each task's outcome in the manifest. This is the
one place that knows how a ScrapeResult maps to files -- scrapers never
touch the filesystem directly, they just return data.
"""

from config import MIN_REVIEWS_PER_BOOK
import manifest
import naming
from metadata_writer import MetadataWriter
from scrapers.base import ScrapeResult


def save_result(result: ScrapeResult, metadata_writer: MetadataWriter) -> None:
    isbn13, source = result.isbn13, result.source

    _save_metadata(result, metadata_writer)
    _save_coverpages(result)
    _save_blurb(result)
    _save_reviews(result)
    # No separate genres file -- genre is folded into the metadata entry's
    # "Genre" field (see _save_metadata / scrapers populate result.metadata["Genre"]).


def _save_metadata(result: ScrapeResult, writer: MetadataWriter) -> None:
    isbn13, source = result.isbn13, result.source
    if result.metadata:
        writer.add_entry(result.metadata)
        manifest.mark(isbn13, source, "metadata", manifest.STATUS_DONE)
    else:
        detail = result.errors.get("metadata", "no metadata returned")
        print(f"WARNING [{source}] {isbn13}: metadata missing -- {detail}")
        manifest.mark(isbn13, source, "metadata", manifest.STATUS_FAILED, detail)


def _save_coverpages(result: ScrapeResult) -> None:
    isbn13, source = result.isbn13, result.source
    if result.cover_images:
        for n, img_bytes in enumerate(result.cover_images, start=1):
            path = naming.coverpage_path(isbn13, source, n)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(img_bytes)
        manifest.mark(isbn13, source, "coverpage", manifest.STATUS_DONE, f"{len(result.cover_images)} image(s)")
    else:
        detail = result.errors.get("coverpage", "no cover image returned")
        print(f"WARNING [{source}] {isbn13}: cover image missing -- {detail}")
        manifest.mark(isbn13, source, "coverpage", manifest.STATUS_FAILED, detail)


def _save_blurb(result: ScrapeResult) -> None:
    isbn13, source = result.isbn13, result.source
    if result.blurb:
        path = naming.blurb_path(isbn13, source)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.blurb, encoding="utf-8")
        manifest.mark(isbn13, source, "blurb", manifest.STATUS_DONE)
    else:
        detail = result.errors.get("blurb", "no blurb returned")
        print(f"WARNING [{source}] {isbn13}: blurb missing -- {detail}")
        manifest.mark(isbn13, source, "blurb", manifest.STATUS_FAILED, detail)


def _save_reviews(result: ScrapeResult) -> None:
    isbn13, source = result.isbn13, result.source
    if result.reviews:
        for n, review_text in enumerate(result.reviews, start=1):
            path = naming.review_path(isbn13, source, n)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(review_text, encoding="utf-8")
        detail = f"{len(result.reviews)} review(s)"
        if len(result.reviews) < MIN_REVIEWS_PER_BOOK:
            detail += f" (below the {MIN_REVIEWS_PER_BOOK} minimum -- source may not have more)"
            print(f"WARNING [{source}] {isbn13}: only {len(result.reviews)}/{MIN_REVIEWS_PER_BOOK} reviews found")
        manifest.mark(isbn13, source, "reviews", manifest.STATUS_DONE, detail)
    else:
        detail = result.errors.get("reviews", "no reviews returned")
        print(f"WARNING [{source}] {isbn13}: reviews missing -- {detail}")
        manifest.mark(isbn13, source, "reviews", manifest.STATUS_FAILED, detail)
