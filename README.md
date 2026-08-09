# Book Data Collection Pipeline

Continues the architecture from the earlier conversation (resumable,
checkpointed, source-parallel) using the folder/metadata spec you locked
in, cross-checked against the actual assignment PDF (`PL_Assginment_1.pdf`)
page images -- not just the text layer, since the file-naming table is
easy to mis-extract.

## What's confirmed vs. what still needs your professor

**Confirmed correct (verified against your real files, not assumed):**
- Your CSV (`230005043.csv`) is 10,000 rows; 9,991 are already clean
  ISBN-13s, 9 are literal `Invalid ISBN-10` placeholders from whatever
  process generated the list. Running `isbn_utils.py` on it gives exactly
  9,991 usable ISBN-13s, 0 conversions needed (there are no raw ISBN-10s
  actually sitting in the file), 9 skipped. `data_cleaned_isbns.csv` is
  the result.
- Metadata file naming: **one JSON array per source**,
  `book_metadata/<source>_metadata.json` (e.g. `goodreads_metadata.json`)
  -- confirmed both by your message and the PDF, this was never actually
  a bug.
- Exact file-naming convention (Section 5, verified against the page
  image because underscores don't survive text extraction reliably):

  | Task | Pattern | Example |
  |---|---|---|
  | Metadata | `<source>_metadata.json` | `goodreads_metadata.json` |
  | Cover page | `<isbn13>_cp_<source>_<n>.jpg` | `9780143127550_cp_goodreads_1.jpg` |
  | Blurb | `<isbn13>_b_<source>_1.txt` | `9780143127550_b_goodreads_1.txt` |
  | Reviews | `<isbn13>_r_<source>_<n>.txt` | `9780143127550_r_goodreads_1.txt` |

  `naming.py` implements these exactly and is tested against the PDF's
  own examples.

**Both open questions from before are now resolved (confirmed with the
professor):**

1. **Genres** live only inside the `"Genre"` field of each
   `book_metadata/<source>_metadata.json` entry. No separate `genres/`
   folder, no per-book genre file -- despite Task 5's written wording,
   this requirement was verbally dropped. `naming.py`/`config.py`/
   `result_saver.py` no longer create or reference a genres folder at all.

2. **Scope is all five sources** -- Goodreads, Amazon, BookBub, Kobo,
   Audible. Matches what was already built (`config.SOURCES`).

Also: reviews must be **individual files, not combined** (Task 4 says so
explicitly) -- so the earlier "aggregate reviews into one JSON to avoid a
million tiny files" idea doesn't apply here; the file-count problem is
real and mandatory, which is exactly why the git-checkpoint strategy
below (zip + Release, don't commit loose files) still matters.

## Structure

**Important: `scrapers/` MUST be an actual subfolder, not flat files.**
Six files (`__init__.py`, `base.py`, `goodreads.py`, `amazon.py`,
`bookbub.py`, `kobo.py`, `audible.py`) belong inside a `scrapers/`
directory sitting next to `pipeline.py` -- the code imports them as
`from scrapers.base import ...` and `from scrapers import SCRAPER_REGISTRY`,
which only works with that exact nesting.

```
Programming_Lab/
├── PL_Assginment_1.pdf
├── 230005043.csv
├── isbn_utils.py
├── config.py             - all paths/sources/timing in one place
├── naming.py              - exact filename patterns, tested against the PDF
├── folder_setup.py        - creates data/{book_metadata,book_coverpage,book_blurb,book_reviews}/
├── manifest.py             - SQLite (isbn13, source, task_type) -> done/failed, resumable
├── metadata_writer.py      - per-source JSON array, atomic writes (crash-safe)
├── result_saver.py         - ScrapeResult -> actual files, per the naming convention
├── pipeline.py             - CLI: single-ISBN mode + full batch mode
├── checkpoint.py           - zip bulk data + commit/push lean metadata, on demand
├── make_test_subset.py     - slices the first N ISBNs for pilot testing
├── requirements.txt
├── README.md
├── data_cleaned_isbns.csv  - the 9,991 usable ISBN-13s, already produced
└── scrapers/
    ├── __init__.py         - SCRAPER_REGISTRY, maps source name -> class
    ├── base.py             - shared interface, rate limiting, retries, lazy Selenium
    ├── goodreads.py        - full worked example (see warning below)
    ├── amazon.py
    ├── bookbub.py
    ├── kobo.py
    └── audible.py          - skeletons, same interface as goodreads.py
```

## Running it

```bash
pip install -r requirements.txt

# Single book (this satisfies the assignment's literal CLI requirement)
python pipeline.py --isbn 9780143127550
python pipeline.py --isbn 9780143127550 --sources goodreads

# Pilot batch: first 50 books, one source at a time to start
python make_test_subset.py 50
python pipeline.py --batch test_50_isbns.csv --sources goodreads

# Full run over your cleaned list, all sources, resumable
python pipeline.py --batch data_cleaned_isbns.csv

# Checkpoint whenever you want (zip bulk data, commit+push lean files)
python checkpoint.py
```

Kill it (Ctrl-C, laptop sleep, crash) at any point and rerun the same
command -- the manifest (`progress_manifest.sqlite3`) skips whatever
already succeeded.

### Testing on the first 50 books

Since the scraper selectors are still unverified TODOs (see below), a
50-book run right now will mostly produce **failed** manifest rows with
clear warning messages -- that's expected, not broken. This pilot run is
still worth doing first, because it validates everything except the
selectors: folder creation, exact file naming, the manifest's resumability,
rate limiting, and that nothing crashes partway through. Recommended order:

1. `python pipeline.py --isbn <one isbn> --sources goodreads` -- get one
   book working end to end first. Open the printed Goodreads URL in your
   browser alongside `scrapers/goodreads.py`, fix the `TODO VERIFY`
   selectors one at a time, rerun, until metadata/blurb/genres/cover
   actually populate.
2. Once Goodreads works for one book, run the 50-book pilot on Goodreads
   only (`--sources goodreads`) to see it hold up at slightly larger
   scale and get a real per-book timing estimate.
3. Repeat step 1 for the other four sources (Amazon last -- see note
   below), then run the 50-book pilot with `--sources all`.
4. Check `python -c "import manifest; manifest.init_manifest(); [print(r) for r in manifest.summary()]"`
   after any run -- it's your at-a-glance pass/fail count per source per task.

## What's real vs. what's a template

Everything **except the actual page-parsing selectors** has been tested
in this environment: folder creation, the manifest's resumability, atomic
metadata writes, and the full save path all ran end-to-end against a
simulated scrape and produced byte-exact matches to the assignment's
naming examples.

The scrapers themselves are a different story -- I have no network access
to goodreads.com, amazon.com, etc. from this sandbox, so **none of the
`soup.select(...)` calls have been run against a live page.**
`scrapers/goodreads.py` is the fullest worked example (the request flow,
retry/rate-limit logic, error handling, and file-saving are all solid),
but every specific selector is marked `TODO VERIFY` and needs you to
open a real book page, inspect the element, and confirm the tag/class
matches. The other four sources are thinner skeletons with the same
interface -- fill in `_parse_*`-style methods following `goodreads.py`'s
pattern once you've inspected each site.

A few source-specific notes worth reading before you start:
- **Goodreads reviews** are loaded via a JS/pagination widget that plain
  `requests` likely can't see past a handful of -- probably your one
  must-use-Selenium case on this source.
- **Amazon** has the strongest anti-bot detection of the five; expect
  more failures/CAPTCHAs here regardless of how correct your code is.
  Test it last, after the pipeline itself is proven on friendlier
  sources.
- **Audible** commonly gates reviews behind an account login, unlike the
  other four's public pages -- confirm with your professor whether
  Audible reviews are actually expected if you hit this wall.

## On GitHub / repo size (numbers double-checked just now, Aug 2026)

The earlier estimate holds: single file 1MB recommended / 100MB hard
block, push size capped at 2GB, repo recommended under 1GB and "strongly
recommended" under 5GB before GitHub reaches out. Git LFS free tier is
still 10 GiB storage + 10 GiB bandwidth/month on Free and Pro (GitHub
moved from prepaid data packs to metered billing since that number was
first quoted, but the free allowance itself hasn't changed) -- confirmed
against GitHub's current billing docs. None of that changes the
recommendation: keep loose scraped files out of git entirely, use
`checkpoint.py` to zip and attach to Releases instead.
