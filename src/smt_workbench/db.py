"""SQLite persistence with one atomic transaction per command."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
 event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, body TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT, attempts INTEGER NOT NULL DEFAULT 1,
 received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE TABLE IF NOT EXISTS boards (
 run_id TEXT NOT NULL, board_id TEXT NOT NULL, line_id TEXT NOT NULL,
 buffer_id TEXT NOT NULL, slot_id TEXT NOT NULL, occupancy_id TEXT NOT NULL,
 state TEXT NOT NULL, expected_sites TEXT NOT NULL,
 PRIMARY KEY(run_id,board_id), UNIQUE(run_id,occupancy_id));
CREATE TABLE IF NOT EXISTS slots (
 run_id TEXT NOT NULL,line_id TEXT NOT NULL,buffer_id TEXT NOT NULL,slot_id TEXT NOT NULL,
 board_id TEXT NOT NULL,occupancy_id TEXT NOT NULL,
 PRIMARY KEY(run_id,line_id,buffer_id,slot_id));
CREATE TABLE IF NOT EXISTS sites (
 run_id TEXT NOT NULL, board_id TEXT NOT NULL, site_id TEXT NOT NULL,
 image_path TEXT, measurement TEXT, prediction TEXT,
 PRIMARY KEY(run_id,board_id,site_id),
 FOREIGN KEY(run_id,board_id) REFERENCES boards(run_id,board_id));
CREATE TABLE IF NOT EXISTS reviews (
 id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,board_id TEXT NOT NULL,
 operator TEXT NOT NULL,note TEXT NOT NULL,decisions TEXT NOT NULL,
 request_id TEXT NOT NULL UNIQUE,body TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(run_id,board_id), FOREIGN KEY(run_id,board_id) REFERENCES boards(run_id,board_id));
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
