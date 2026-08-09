"""
naming.py

Implements the file-naming convention from Section 5 of the assignment
EXACTLY as written (verified against the PDF page image, not just the
text layer, since underscores are easy to lose in PDF text extraction):

    Task            Filename Pattern                  Example
    Book Metadata   <source>_metadata.json            goodreads_metadata.json
    Book Cover Page <isbn13>_cp_<source>_<n>.jpg       9780143127550_cp_goodreads_1.jpg
    Book Blurb      <isbn13>_b_<source>_1.txt          9780143127550_b_goodreads_1.txt
    Book Reviews    <isbn13>_r_<source>_<n>.txt        9780143127550_r_goodreads_1.txt

No genres file/pattern -- genre lives only in the "Genre" field inside each
book_metadata/<source>_metadata.json entry, per the professor's clarification.

Keeping every pattern in one module means a professor-mandated tweak is a
one-file change instead of a grep-and-pray across the codebase.
"""

from config import FOLDERS


def metadata_filename(source: str) -> str:
    return f"{source}_metadata.json"


def coverpage_filename(isbn13: str, source: str, n: int) -> str:
    return f"{isbn13}_cp_{source}_{n}.jpg"


def blurb_filename(isbn13: str, source: str) -> str:
    # Pattern hardcodes "_1" -- the assignment shows no <n> for blurb, so
    # there's implicitly always exactly one blurb file.
    return f"{isbn13}_b_{source}_1.txt"


def review_filename(isbn13: str, source: str, n: int) -> str:
    return f"{isbn13}_r_{source}_{n}.txt"


def metadata_path(source: str):
    return FOLDERS["metadata"] / metadata_filename(source)


def coverpage_path(isbn13: str, source: str, n: int):
    return FOLDERS["coverpage"] / coverpage_filename(isbn13, source, n)


def blurb_path(isbn13: str, source: str):
    return FOLDERS["blurb"] / blurb_filename(isbn13, source)


def review_path(isbn13: str, source: str, n: int):
    return FOLDERS["reviews"] / review_filename(isbn13, source, n)
