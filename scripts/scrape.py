"""
CrackAB ACT scraper → local SQLite.

Local DB only. NOT for direct republication on a Stripe-paywalled product
without further legal review (CrackAB claims © Max, official ACT tests are
ACT, Inc.'s IP). Use this DB as a starting reference for your own AI-generated
question bank, or for personal practice.

Polite scrape: 1.2 sec/request, resumable, logs progress.
Run:  python3 scrape.py [--sections english,math] [--limit 5]
"""
import argparse
import json
import re
import sqlite3
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.crackab.com"
DB_PATH = "/Users/jasperlasser/actprep-crackab/crackab.db"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 1.2  # polite delay between requests

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# ─── DB ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tests (
      id INTEGER PRIMARY KEY,
      section TEXT NOT NULL,
      test_number INTEGER,
      title TEXT,
      url TEXT,
      passage_html TEXT,
      scraped_at TEXT
    );
    CREATE TABLE IF NOT EXISTS questions (
      test_id INTEGER NOT NULL,
      q_num INTEGER NOT NULL,
      options_json TEXT,
      correct_answer TEXT,
      PRIMARY KEY (test_id, q_num),
      FOREIGN KEY (test_id) REFERENCES tests(id)
    );
    """)
    conn.commit()
    return conn

# ─── Discovery ─────────────────────────────────────────────────────
def get_test_links(section):
    """Return list of (test_id, test_number, url) tuples for a section."""
    url = f"{BASE}/act/{section}/"
    r = session.get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        m = re.match(r"/act/" + section + r"/test(\d+)\.html$", a["href"])
        if m:
            test_id = int(m.group(1))
            text = a.get_text(strip=True)
            # try to pull "Practice Test N"
            num_m = re.search(r"Test\s+(\d+)", text)
            num = int(num_m.group(1)) if num_m else None
            links.append((test_id, num, urljoin(BASE, a["href"])))
    # de-dupe
    seen = set()
    unique = []
    for t in links:
        if t[0] not in seen:
            seen.add(t[0])
            unique.append(t)
    return unique

# ─── Parse one test page ───────────────────────────────────────────
def parse_test_page(html, section):
    """Return (title, form_html, passage_div_html, questions[{q_num, options}]).

    Test pages have a two-column layout:
      - col-md-7: the form with radio inputs (one per question)
      - col-md-5: <div id="mypassage"> with the actual passage text
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", {"name": "TEST"})
    if not form:
        return None, None, None, []
    title = form.find("input", {"name": "title"})
    title = title["value"] if title else ""
    passage_html = str(form)  # keep "passage_html" name for backwards compat
    # Section-aware passage extraction (each section uses different containers).
    if section == "english":
        p = soup.find("div", id="mypassage")
        passage_div_html = str(p) if p else ""
    elif section == "reading":
        p = soup.find("div", class_="mypassage")
        passage_div_html = str(p) if p else ""
    elif section == "science":
        blocks = soup.find_all("div", class_="mymessage")
        passage_div_html = (
            '<div class="science-passages">' + "".join(str(b) for b in blocks) + "</div>"
            if blocks else ""
        )
    else:  # math etc.
        passage_div_html = ""
    # Rewrite relative image URLs to absolute so they render when served locally.
    if passage_div_html:
        passage_div_html = re.sub(
            r'src="(/[^"]+)"',
            lambda m: f'src="{BASE}{m.group(1)}"',
            passage_div_html,
        )

    # parse options per question
    questions = {}
    for inp in form.find_all("input", {"type": "radio"}):
        qnum_str = inp.get("name", "")
        if not qnum_str.isdigit():
            continue
        qnum = int(qnum_str)
        val = inp.get("value", "").strip()
        if not val:
            continue
        # the option label text usually follows the input as a sibling text node
        # we just store the option letters and try to grab labels from nearby text
        # the actual option text isn't always cleanly attached, so we capture
        # whatever text follows until the next <input>.
        sib_txt = []
        for sib in inp.next_siblings:
            if getattr(sib, "name", None) == "input":
                break
            if hasattr(sib, "get_text"):
                t = sib.get_text(" ", strip=True)
            else:
                t = str(sib).strip()
            if t:
                sib_txt.append(t)
        opt_text = " ".join(sib_txt).strip()
        # strip leading letter+dot prefix if present (e.g. "A. NO CHANGE")
        opt_text = re.sub(r"^[A-J]\.\s*", "", opt_text)
        questions.setdefault(qnum, {})[val] = opt_text

    qlist = []
    for qnum in sorted(questions.keys()):
        qlist.append({"q_num": qnum, "options": questions[qnum]})
    return title, passage_html, passage_div_html, qlist

# ─── Get answer key via /results.php ───────────────────────────────
def get_answer_key(test_id, section, num_qs=15):
    """POST a dummy submission, parse the answer column from the response."""
    data = {
        "title": f"ACT {section.title()} practice test",
        "id": str(test_id),
        "type": section,
    }
    # send dummy A/F answers for each
    for i in range(1, num_qs + 1):
        data[str(i)] = "A" if i % 2 == 1 else "F"
    r = session.post(
        f"{BASE}/results.php",
        data=data,
        headers={"Referer": f"{BASE}/act/{section}/test{test_id}.html"},
        timeout=20,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # results table has rows: Question | Correct | Your | Result | Explanation
    answers = {}
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= 3 and cells[0].isdigit():
            qnum = int(cells[0])
            correct = cells[1].strip()
            if correct and len(correct) == 1 and correct in "ABCDEFGHIJK":
                answers[qnum] = correct
    return answers

# ─── Scrape one test ───────────────────────────────────────────────
def scrape_test(conn, section, test_id, test_num, url):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM tests WHERE id = ?", (test_id,))
    if cur.fetchone():
        return "skipped (already scraped)"
    r = session.get(url, timeout=20)
    if r.status_code != 200:
        return f"page HTTP {r.status_code}"
    title, passage_html, passage_div_html, questions = parse_test_page(r.text, section)
    if not questions:
        return "no questions parsed"
    time.sleep(SLEEP)
    answers = get_answer_key(test_id, section, num_qs=len(questions))
    # write
    cur.execute(
        "INSERT INTO tests (id, section, test_number, title, url, passage_html, passage_div_html, scraped_at) VALUES (?,?,?,?,?,?,?,?)",
        (test_id, section, test_num, title, url, passage_html, passage_div_html, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    for q in questions:
        cur.execute(
            "INSERT OR REPLACE INTO questions (test_id, q_num, options_json, correct_answer) VALUES (?,?,?,?)",
            (test_id, q["q_num"], json.dumps(q["options"]), answers.get(q["q_num"])),
        )
    conn.commit()
    return f"OK ({len(questions)} q, {len([a for a in answers.values() if a])} answers)"

# ─── Main ──────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", default="english,math,reading,science")
    ap.add_argument("--limit", type=int, default=None,
                    help="Per-section cap; useful for smoke tests")
    args = ap.parse_args()

    conn = init_db()
    sections = args.sections.split(",")
    total_attempted = 0
    total_ok = 0

    for section in sections:
        print(f"\n=== {section.upper()} ===", flush=True)
        try:
            tests = get_test_links(section)
        except Exception as e:
            print(f"  index fetch failed: {e}", flush=True)
            continue
        if args.limit:
            tests = tests[: args.limit]
        print(f"  {len(tests)} tests discovered", flush=True)
        time.sleep(SLEEP)
        for i, (test_id, test_num, url) in enumerate(tests, 1):
            total_attempted += 1
            try:
                result = scrape_test(conn, section, test_id, test_num, url)
                ok = result.startswith("OK")
                if ok:
                    total_ok += 1
                print(f"  [{i:>3}/{len(tests)}] test{test_id} → {result}", flush=True)
            except Exception as e:
                print(f"  [{i:>3}/{len(tests)}] test{test_id} → ERROR {e}", flush=True)
            time.sleep(SLEEP)

    print(f"\n=== DONE: {total_ok}/{total_attempted} tests scraped → {DB_PATH}", flush=True)

if __name__ == "__main__":
    main()
