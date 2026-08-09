"""
pipeline.py

Two ways to run this, both using the exact same scraping code underneath:

  Single book (satisfies the assignment's literal requirement: "must
  accept an ISBN-13 as input ... and work for any valid ISBN-13, not
  just one hardcoded example"):

      python pipeline.py --isbn 9780143127550
      python pipeline.py --isbn 9780143127550 --sources goodreads,kobo

  Full batch run over your cleaned 9,991-book list, resumable, one
  thread per source running concurrently, each thread serial + delayed
  within itself (per the earlier discussion: the "1-2s between
  consecutive requests" reads as per-server, so 5 sources in parallel
  isn't overloading any single one of them):

      python pipeline.py --batch data_cleaned_isbns.csv
      python pipeline.py --batch data_cleaned_isbns.csv --sources goodreads

  Either mode is safe to Ctrl-C and rerun -- the manifest skips whatever
  already succeeded.
"""

import argparse
import csv
import sys
import threading

import config
import manifest
from folder_setup import setup_folders
from metadata_writer import MetadataWriter
from result_saver import save_result
from scrapers import SCRAPER_REGISTRY


def process_one(isbn13: str, source: str, writer: MetadataWriter, scraper=None) -> None:
    """Scrape+save a single (isbn13, source) pair. Reuses `scraper` if given
    (batch mode keeps one scraper instance alive per source); opens and
    closes its own otherwise (single-book mode)."""
    owns_scraper = scraper is None
    if owns_scraper:
        scraper = SCRAPER_REGISTRY[source]()
    try:
        result = scraper.scrape_book(isbn13)
        save_result(result, writer)
    finally:
        if owns_scraper:
            scraper.close()


def run_single(isbn13: str, sources: list[str]) -> None:
    setup_folders()
    manifest.init_manifest()
    for source in sources:
        print(f"\n=== {source} ===")
        writer = MetadataWriter(source)
        process_one(isbn13, source, writer)
        print(f"  metadata written to {writer.path} ({len(writer)} total entries in that file)")


def run_source_worker(source: str, isbns: list[str]) -> None:
    """Runs in its own thread. Serial within this source, with the
    scraper's built-in per-request delay -- see BaseScraper._throttle."""
    writer = MetadataWriter(source)
    with SCRAPER_REGISTRY[source]() as scraper:
        for i, isbn13 in enumerate(isbns, start=1):
            # Skip a book only if EVERY task succeeded, not just metadata --
            # otherwise a book whose metadata worked but whose reviews
            # failed (true for your whole 50-book run before this fix)
            # would be skipped forever and reviews would never get retried.
            # scrape_book() re-fetches the page on retry, which is a small
            # amount of repeated work for tasks that already succeeded, but
            # it's the simplest correct fix -- scrape_book() returns one
            # combined result for all four tasks per fetch, so there's no
            # cheaper way to retry just the failed piece without a bigger
            # restructuring of the scraper interface.
            all_done = all(manifest.is_done(isbn13, source, t) for t in manifest.TASK_TYPES)
            if all_done and writer.has_entry(isbn13):
                continue  # every task already succeeded in a previous run
            try:
                process_one(isbn13, source, writer, scraper=scraper)
            except Exception as e:
                # Only genuine infrastructure failures should reach here --
                # scrapers are expected to catch per-field issues themselves.
                print(f"ERROR [{source}] {isbn13}: unhandled exception -- {e}")
                manifest.mark(isbn13, source, "metadata", manifest.STATUS_FAILED, f"unhandled: {e}")
            if i % config.CHECKPOINT_EVERY_N_BOOKS == 0:
                print(f"[{source}] checkpoint: {i}/{len(isbns)} books attempted")


def run_batch(csv_path: str, sources: list[str]) -> None:
    setup_folders()
    manifest.init_manifest()

    with open(csv_path, newline="", encoding="utf-8") as f:
        isbns = [row["Isbn-13"] for row in csv.DictReader(f)]
    print(f"Loaded {len(isbns)} ISBN-13s from {csv_path}")
    print(f"Sources: {', '.join(sources)} (one thread each, running concurrently)")

    threads = [
        threading.Thread(target=run_source_worker, args=(source, isbns), name=source)
        for source in sources
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n=== Run complete. Manifest summary (source, task, status, count): ===")
    for source, task_type, status, count in manifest.summary():
        print(f"  {source:10s} {task_type:10s} {status:8s} {count}")


def main():
    parser = argparse.ArgumentParser(description="Book data scraping pipeline")
    parser.add_argument("--isbn", help="Scrape a single ISBN-13 (satisfies the assignment's CLI requirement)")
    parser.add_argument("--batch", help="Path to a cleaned CSV (one 'Isbn-13' column) for the full run")
    parser.add_argument(
        "--sources", default="all",
        help="Comma-separated source list, or 'all' (default). Options: " + ", ".join(config.SOURCES),
    )
    args = parser.parse_args()

    if not args.isbn and not args.batch:
        parser.error("pass either --isbn <isbn13> or --batch <csv path>")

    sources = config.SOURCES if args.sources == "all" else [s.strip() for s in args.sources.split(",")]
    unknown = set(sources) - set(config.SOURCES)
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}. Options: {', '.join(config.SOURCES)}")

    if args.isbn:
        run_single(args.isbn, sources)
    else:
        run_batch(args.batch, sources)


if __name__ == "__main__":
    main()
