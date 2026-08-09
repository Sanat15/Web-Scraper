"""
isbn_utils.py

Validates ISBN-10 / ISBN-13 strings and converts ISBN-10 -> ISBN-13.
The conversion is a pure checksum calculation (no network / lookup needed):
drop the ISBN-10 check digit, prepend "978" to the remaining 9 digits,
then compute a fresh ISBN-13 check digit.

CLI usage (cleans a CSV with a column named "Isbn-13"):
    python isbn_utils.py input.csv cleaned_output.csv
"""

import re
import sys
import csv


def _clean(raw: str) -> str:
    """Strip anything that isn't a digit or a trailing X."""
    return re.sub(r"[^0-9Xx]", "", str(raw)).upper()


def is_valid_isbn10(isbn: str) -> bool:
    isbn = _clean(isbn)
    if len(isbn) != 10 or not isbn[:9].isdigit() or isbn[9] not in "0123456789X":
        return False
    total = sum((10 if ch == "X" else int(ch)) * (10 - i) for i, ch in enumerate(isbn))
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    isbn = _clean(isbn)
    if len(isbn) != 13 or not isbn.isdigit():
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(isbn[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(isbn[12])


def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert a valid ISBN-10 string to its ISBN-13 equivalent."""
    isbn10 = _clean(isbn10)
    if not is_valid_isbn10(isbn10):
        raise ValueError(f"Not a valid ISBN-10: {isbn10}")
    core = "978" + isbn10[:9]  # the ISBN-10 check digit is simply discarded
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core))
    check = (10 - (total % 10)) % 10
    return core + str(check)


def normalize(raw: str):
    """
    Resolve one raw CSV cell to (isbn13_or_None, status).
    status: 'already_isbn13' | 'converted_from_isbn10' | 'unusable'
    """
    cleaned = _clean(raw)
    if is_valid_isbn13(cleaned):
        return cleaned, "already_isbn13"
    if is_valid_isbn10(cleaned):
        return isbn10_to_isbn13(cleaned), "converted_from_isbn10"
    return None, "unusable"


def _self_test():
    # Standard textbook example: 0-306-40615-2 -> 978-0-306-40615-7
    assert is_valid_isbn10("0306406152")
    assert isbn10_to_isbn13("0306406152") == "9780306406157"
    assert is_valid_isbn13("9780306406157")
    assert normalize("Invalid ISBN-10") == (None, "unusable")


if __name__ == "__main__":
    _self_test()

    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        rows_out = []
        stats = {"already_isbn13": 0, "converted_from_isbn10": 0, "unusable": 0}

        for row in reader:
            raw = row.get("Isbn-13", "")
            isbn13, status = normalize(raw)
            stats[status] += 1
            if isbn13:
                rows_out.append(isbn13)
            else:
                print(f"WARNING: could not resolve '{raw}' to a valid ISBN-13 - skipping")

    with open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["Isbn-13"])
        for isbn in rows_out:
            writer.writerow([isbn])

    print(f"\nSelf-test passed. Done: {len(rows_out)} usable ISBN-13s written to {out_path}")
    print(f"  already ISBN-13       : {stats['already_isbn13']}")
    print(f"  converted from ISBN-10: {stats['converted_from_isbn10']}")
    print(f"  unusable / skipped     : {stats['unusable']}")
