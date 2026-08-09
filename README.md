# Book Data Collection - Scraped Data Submission

This repository currently contains only the **scraped dataset** produced
for the book data collection assignment (`PL_Assginment_1.pdf`). The
scraping code itself is intentionally not part of this submission right
now and will be added separately if the professor asks for it.

## Current scope

- **Source scraped so far:** Goodreads only. Amazon, BookBub, Kobo, and
  Audible have not been started yet.
- **Books scraped so far:** ~100, out of the full 9,991-book cleaned list.
- This is a **live, growing dataset** -- more books get added to `data/`
  in batches as scraping continues, not a one-time final dump.

## Folder structure

```
data/
├── book_metadata/
│   └── goodreads_metadata.json        (one JSON array, one entry per book)
├── book_coverpage/
│   └── <isbn13>_cp_goodreads_<n>.jpg
├── book_blurb/
│   └── <isbn13>_b_goodreads_1.txt
└── book_reviews/
    └── <isbn13>_r_goodreads_<n>.txt    (each review its own file)
```

## File naming convention

| Task | Pattern | Example |
|---|---|---|
| Metadata | `<source>_metadata.json` | `goodreads_metadata.json` |
| Cover page | `<isbn13>_cp_<source>_<n>.jpg` | `9780143127550_cp_goodreads_1.jpg` |
| Blurb | `<isbn13>_b_<source>_1.txt` | `9780143127550_b_goodreads_1.txt` |
| Reviews | `<isbn13>_r_<source>_<n>.txt` | `9780143127550_r_goodreads_1.txt` |

Each entry in `goodreads_metadata.json` holds: ISBN-13, Author(s), Title,
Publisher, Origin/Country of publication, Date of publication, Language,
and Genre (comma-separated). Genre is stored as a metadata field, not a
separate folder/file, per the professor's confirmation.

## Note on gaps

Not every book has every field or file -- some Goodreads editions
genuinely have no listed publisher, language, cover image, or reviews.
Where that's the case, it's skipped rather than faked. This is expected
and matches Goodreads' own data, not a scraping bug.
