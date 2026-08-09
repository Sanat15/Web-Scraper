"""
verify_next_data.py

Run this against the debug_page.html you already generated, BEFORE
swapping in the updated goodreads.py, to confirm the __NEXT_DATA__
extraction actually works on your exact saved file (not just my
reconstruction of it).

Usage:
    python verify_next_data.py debug_page.html
"""

import json
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup


def resolve(ref, apollo):
    if isinstance(ref, dict) and "__ref" in ref:
        return apollo.get(ref["__ref"])
    return ref


def main(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        print("FAIL: no <script id=\"__NEXT_DATA__\"> tag found in this file.")
        print("      Either this page doesn't use it, or it's a different site/layout.")
        sys.exit(1)

    try:
        next_data = json.loads(script.string)
    except json.JSONDecodeError as e:
        print(f"FAIL: __NEXT_DATA__ found but not valid JSON: {e}")
        sys.exit(1)

    print("OK: __NEXT_DATA__ found and parsed as JSON.\n")

    try:
        apollo = next_data["props"]["pageProps"]["apolloState"]
    except (KeyError, TypeError):
        print("FAIL: JSON parsed, but props.pageProps.apolloState is missing.")
        print("      Goodreads may have changed their page structure.")
        sys.exit(1)

    root = apollo.get("ROOT_QUERY", {})
    book_ref = None
    for key, value in root.items():
        if key.startswith("getBookByLegacyId") and isinstance(value, dict) and "__ref" in value:
            book_ref = value
            break

    if book_ref is None:
        print("FAIL: no getBookByLegacyId(...) key found in ROOT_QUERY.")
        sys.exit(1)

    book = resolve(book_ref, apollo)
    if not book:
        print("FAIL: book reference didn't resolve to an object in apolloState.")
        sys.exit(1)

    details = book.get("details") or {}
    authors = []
    primary = book.get("primaryContributorEdge")
    if primary:
        node = resolve(primary.get("node"), apollo)
        if node and node.get("name"):
            authors.append(node["name"])
    for edge in book.get("secondaryContributorEdges") or []:
        node = resolve(edge.get("node"), apollo)
        if node and node.get("name"):
            authors.append(node["name"])

    genres = [bg["genre"]["name"] for bg in book.get("bookGenres") or [] if bg.get("genre", {}).get("name")]

    pub_date = None
    pub_ms = details.get("publicationTime")
    if isinstance(pub_ms, (int, float)):
        pub_date = datetime.fromtimestamp(pub_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    description_html = book.get("description")
    blurb = BeautifulSoup(description_html, "html.parser").get_text(" ").strip()[:120] + "..." if description_html else None

    review_edges = (root.get("getReviews") or {}).get("edges", [])
    review_texts = []
    for edge in review_edges:
        node = resolve(edge.get("node"), apollo)
        if node and node.get("text"):
            review_texts.append(BeautifulSoup(node["text"], "html.parser").get_text(" ").strip())

    print("Extracted from your real debug_page.html:")
    print(f"  Title:              {book.get('title')}")
    print(f"  Author(s):          {', '.join(authors) or None}")
    print(f"  Publisher:          {details.get('publisher')}")
    print(f"  ISBN-13:            {details.get('isbn13')}")
    print(f"  Language:           {(details.get('language') or {}).get('name')}")
    print(f"  Date of publication:{pub_date}")
    print(f"  Genres ({len(genres)}):        {genres}")
    print(f"  Cover image URL:    {book.get('imageUrl')}")
    print(f"  Blurb (first 120c): {blurb}")
    print(f"  Reviews found:      {len(review_texts)} (need >= 25 per the assignment)")
    if review_texts:
        print(f"  First review starts: {review_texts[0][:80]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_next_data.py <path to debug_page.html>")
        sys.exit(1)
    main(sys.argv[1])
