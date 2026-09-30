"""SQLite storage for robot run records.

Kept on the standard library so the dashboard has no database dependency.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pass','fail','warn')),
    metric      REAL,
    message     TEXT NOT NULL DEFAULT '',
    payload     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project, id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status, id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def cursor(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["payload"] = json.loads(d["payload"])
    return d
