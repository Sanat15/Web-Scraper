"""
manifest.py

The resumable-pipeline backbone described earlier: a single table logging
(isbn13, source, task_type) -> status, checked before each scrape and
updated after. This is what turns "200 fragile manual batches" into one
script you can kill and rerun at any point.

Task-level granularity (not per-review) keeps the table small: ~9,991
books x 5 sources x 4 task types is under 200k rows even at full scope,
comfortably fine for SQLite. Reviews are tracked as ONE 'reviews' row per
(isbn13, source) meaning "the review-collection step ran", not one row
per review file.

Thread-safety: each source runs in its own thread (see pipeline.py) and
every thread gets its own sqlite3 connection (SQLite connections aren't
safe to share across threads) -- writes are additionally serialized with
a module-level lock since SQLite only allows one writer at a time anyway.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from config import MANIFEST_DB

TASK_TYPES = ("metadata", "coverpage", "blurb", "reviews")
STATUS_DONE = "done"
STATUS_FAILED = "failed"

_write_lock = threading.Lock()
_thread_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """One connection per thread (SQLite connections are not thread-safe)."""
    if not hasattr(_thread_local, "conn"):
        _thread_local.conn = sqlite3.connect(str(MANIFEST_DB))
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
    return _thread_local.conn


def init_manifest() -> None:
    conn = _get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            isbn13     TEXT NOT NULL,
            source     TEXT NOT NULL,
            task_type  TEXT NOT NULL,
            status     TEXT NOT NULL,
            detail     TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (isbn13, source, task_type)
        )
        """
    )
    conn.commit()


def is_done(isbn13: str, source: str, task_type: str) -> bool:
    conn = _get_conn()
    row = conn.execute(
        "SELECT status FROM progress WHERE isbn13=? AND source=? AND task_type=?",
        (isbn13, source, task_type),
    ).fetchone()
    return row is not None and row[0] == STATUS_DONE


def mark(isbn13: str, source: str, task_type: str, status: str, detail: str = "") -> None:
    assert task_type in TASK_TYPES, f"unknown task_type: {task_type}"
    conn = _get_conn()
    with _write_lock:
        conn.execute(
            """
            INSERT INTO progress (isbn13, source, task_type, status, detail, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(isbn13, source, task_type)
            DO UPDATE SET status=excluded.status, detail=excluded.detail, updated_at=excluded.updated_at
            """,
            (isbn13, source, task_type, status, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def failures(source: str = None):
    """Everything currently marked failed -- your retry queue / grading-time failure log."""
    conn = _get_conn()
    if source:
        rows = conn.execute(
            "SELECT isbn13, source, task_type, detail FROM progress WHERE status=? AND source=?",
            (STATUS_FAILED, source),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT isbn13, source, task_type, detail FROM progress WHERE status=?",
            (STATUS_FAILED,),
        ).fetchall()
    return rows


def summary():
    """Counts per (source, task_type, status) -- a quick health check on a running job."""
    conn = _get_conn()
    return conn.execute(
        """
        SELECT source, task_type, status, COUNT(*)
        FROM progress
        GROUP BY source, task_type, status
        ORDER BY source, task_type, status
        """
    ).fetchall()
