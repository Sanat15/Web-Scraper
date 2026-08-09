"""
metadata_writer.py

Handles the "5 JSON files, one per source, one big array of book objects
each" format you specified. Each source has exactly ONE writer thread in
this design (see pipeline.py), so there's no cross-thread race on a given
file -- but the write itself is still made atomic (write-to-temp, then
os.replace) so a crash or kill mid-write can never leave a half-written,
corrupt JSON file behind. That matters here because with 9,991 entries
per file you cannot afford to lose the whole file to one bad shutdown.
"""

import json
import os
import tempfile
from pathlib import Path

from naming import metadata_path


class MetadataWriter:
    def __init__(self, source: str):
        self.source = source
        self.path: Path = metadata_path(source)
        self._entries: dict[str, dict] = {}  # keyed by ISBN-13 to dedupe on resume
        self._load_existing()

    def _load_existing(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                for entry in existing:
                    isbn = entry.get("ISBN-13")
                    if isbn:
                        self._entries[isbn] = entry
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARNING: could not read existing {self.path} ({e}); starting fresh in memory. "
                      f"The file on disk is left untouched until the next successful write.")

    def has_entry(self, isbn13: str) -> bool:
        return isbn13 in self._entries

    def add_entry(self, entry: dict) -> None:
        """entry must contain 'ISBN-13' plus the other METADATA_FIELDS keys."""
        isbn = entry.get("ISBN-13")
        if not isbn:
            raise ValueError("entry is missing 'ISBN-13'")
        self._entries[isbn] = entry
        self._flush()

    def _flush(self) -> None:
        """Atomic write: temp file in the same directory, then os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = list(self._entries.values())
        fd, tmp_path = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)  # atomic on POSIX
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def __len__(self) -> int:
        return len(self._entries)
