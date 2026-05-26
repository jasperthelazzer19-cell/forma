"""SQLite connection + first-boot seeding.

DB lives at data/crackab.db in dev. On Railway (or any volume-backed deploy),
set DATABASE_PATH=/data/crackab.db — we'll seed the bundled snapshot on first boot.
"""
import os
import shutil
import sqlite3
from flask import g

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SEED_DB = os.path.join(_REPO_ROOT, "data", "crackab.db")

DB_PATH = os.environ.get("DATABASE_PATH", _SEED_DB)


def seed_if_needed():
    """Copy bundled snapshot to the runtime DB path the first time the process starts."""
    if DB_PATH != _SEED_DB and os.path.exists(_SEED_DB) and not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        shutil.copy2(_SEED_DB, DB_PATH)
        print(f" * Seeded DB → {DB_PATH}", flush=True)


def db():
    """Return a per-request SQLite connection, cached on Flask's g."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_=None):
    d = g.pop("db", None)
    if d:
        d.close()
