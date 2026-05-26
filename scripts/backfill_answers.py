"""Backfill correct_answer for tests where the original scrape failed.

The original scraper POSTed dummy answers with form keys "1"-"15", but
crackab's radio inputs are named with the global question ID (e.g. "991"-
"1005" or "1051"-"1065"). The endpoint silently returned no answers when
the keys didn't match. This script re-POSTs using the actual q_num values
stored in the DB.
"""
import sqlite3
import time
import requests
from bs4 import BeautifulSoup

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
BASE = "https://www.crackab.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 0.9

s = requests.Session()
s.headers.update({"User-Agent": UA})


def get_answers(test_id, section, q_nums):
    """POST dummy answers using the actual radio names. Returns dict q_num→letter."""
    data = {
        "title": f"ACT {section.title()} practice test",
        "id": str(test_id),
        "type": section,
    }
    # Use the ACTUAL stored q_num values as the form keys
    for i, q in enumerate(sorted(q_nums)):
        data[str(q)] = "A" if i % 2 == 0 else "F"
    r = s.post(
        f"{BASE}/results.php",
        data=data,
        headers={"Referer": f"{BASE}/act/{section}/test{test_id}.html"},
        timeout=20,
    )
    if r.status_code != 200:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    answers = {}
    sorted_qs = sorted(q_nums)
    position = 0  # rows come back in the same order as the form's questions
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 3 and cells[0].isdigit():
            # First column is crackab's displayed Q number (could be 1-15,
            # 16-30, etc.) — we don't trust it; we match positionally.
            correct = cells[1].strip()
            if correct and len(correct) == 1 and correct in "ABCDEFGHIJK":
                if position < len(sorted_qs):
                    answers[sorted_qs[position]] = correct
            position += 1
    return answers


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.id, t.section, t.url
        FROM tests t
        WHERE NOT EXISTS (
            SELECT 1 FROM questions q
            WHERE q.test_id = t.id AND q.correct_answer IS NOT NULL
        )
        ORDER BY t.section, t.id
    """).fetchall()
    print(f"{len(rows)} tests missing answers")
    ok = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        tid = row["id"]
        qs = conn.execute(
            "SELECT q_num FROM questions WHERE test_id = ? ORDER BY q_num", (tid,)
        ).fetchall()
        q_nums = [q["q_num"] for q in qs]
        if not q_nums:
            continue
        try:
            answers = get_answers(tid, row["section"], q_nums)
            if answers:
                for q_num, letter in answers.items():
                    conn.execute(
                        "UPDATE questions SET correct_answer = ? WHERE test_id = ? AND q_num = ?",
                        (letter, tid, q_num),
                    )
                conn.commit()
                ok += 1
            if i % 10 == 0 or i == len(rows):
                elapsed = int(time.time() - t0)
                eta = int(elapsed / i * (len(rows) - i)) if i else 0
                print(f"  [{i:>3}/{len(rows)}] test{tid} ({row['section']}) → {len(answers)} answers · {elapsed}s, ~{eta//60}m{eta%60}s left", flush=True)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  [{i}] test{tid} → ERROR {e}", flush=True)
    print(f"DONE: {ok}/{len(rows)} tests got answers", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
