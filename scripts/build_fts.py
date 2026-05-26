"""
Build a SQLite FTS5 virtual table mirroring question text (prompt + options).
Runs once + on demand; subsequent searches hit FTS5 directly.

Schema:
  questions_fts(test_id, q_num, section, body)

Maintained out-of-band via this script. (We could add triggers, but for a
read-mostly DB a periodic rebuild is simpler.)
"""
import json
import sqlite3
import time

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"


def build(conn):
    cur = conn.cursor()
    # Drop & rebuild the FTS table — simpler than incremental sync
    cur.execute("DROP TABLE IF EXISTS questions_fts")
    cur.execute("""CREATE VIRTUAL TABLE questions_fts USING fts5(
        test_id UNINDEXED,
        q_num UNINDEXED,
        section UNINDEXED,
        body,
        tokenize='porter unicode61'
    )""")
    # Populate
    t0 = time.time()
    n = 0
    BATCH = 1000
    rows_buf = []
    cur2 = conn.cursor()
    for r in cur2.execute("""
        SELECT q.test_id, q.q_num, q.options_json, t.section
        FROM questions q JOIN tests t ON t.id = q.test_id
    """):
        try:
            opts = json.loads(r[2] or "{}")
        except Exception:
            continue
        prompt = (opts.get("_prompt") or "")
        opt_texts = " ".join(v for k, v in opts.items() if len(k) == 1 and isinstance(v, str))
        body = (prompt + " " + opt_texts).strip()
        if not body:
            continue
        rows_buf.append((r[0], r[1], r[3], body))
        if len(rows_buf) >= BATCH:
            cur.executemany("INSERT INTO questions_fts(test_id, q_num, section, body) VALUES (?,?,?,?)", rows_buf)
            n += len(rows_buf)
            rows_buf = []
    if rows_buf:
        cur.executemany("INSERT INTO questions_fts(test_id, q_num, section, body) VALUES (?,?,?,?)", rows_buf)
        n += len(rows_buf)
    conn.commit()
    elapsed = time.time() - t0
    print(f"FTS5 built: {n} questions indexed in {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    build(conn)
