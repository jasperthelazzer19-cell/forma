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


def repair_fts():
    """Repopulate the FTS search index if it has drifted from `questions`
    (some rows were never indexed, so they were unsearchable). Idempotent — a
    no-op once the index matches the join-able question count — and wrapped so a
    failure can never block startup."""
    import json
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA busy_timeout=8000")
        # Only questions that join to a real test are searchable, so compare to
        # that count (not raw questions) — otherwise orphans force a rebuild every boot.
        expected = conn.execute(
            "SELECT COUNT(*) FROM questions q JOIN tests t ON t.id=q.test_id").fetchone()[0]
        have = conn.execute("SELECT COUNT(*) FROM questions_fts").fetchone()[0]
        if expected == have:
            conn.close(); return
        rows = conn.execute(
            "SELECT q.test_id, q.q_num, t.section, q.options_json "
            "FROM questions q JOIN tests t ON t.id=q.test_id").fetchall()
        conn.execute("DELETE FROM questions_fts")
        for test_id, q_num, section, oj in rows:
            try:
                opts = json.loads(oj or "{}")
            except Exception:
                opts = {}
            body = ((opts.get("_prompt") or "") + " "
                    + " ".join(str(v) for k, v in opts.items() if len(k) == 1)).strip()
            conn.execute(
                "INSERT INTO questions_fts(test_id, q_num, section, body) VALUES (?,?,?,?)",
                (test_id, q_num, section, body))
        conn.commit()
        print(f" * Rebuilt FTS index: {expected} questions indexed (was {have})", flush=True)
        conn.close()
    except Exception as e:
        print(f" * FTS repair skipped: {e}", flush=True)


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
