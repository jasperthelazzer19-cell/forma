"""
Scrape actexam.net — sister site to crackab.com, same Max owner, same HTML
structure. Re-use the same scraper module shape.

Stores tests with source='actexam' so they're distinguishable from crackab.
"""
import json
import re
import sqlite3
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.actexam.net"
DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 1.0

s = requests.Session()
s.headers.update({"User-Agent": UA})


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE tests ADD COLUMN source TEXT DEFAULT 'crackab'")
    conn.commit()


def get_test_links(section):
    url = f"{BASE}/act/{section}/"
    try:
        r = s.get(url, timeout=20)
        if r.status_code != 200:
            print(f"  index {section}: HTTP {r.status_code}", flush=True)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            m = re.match(r"/act/" + section + r"/test(\d+)\.html$", a["href"])
            if m:
                tid = int(m.group(1))
                if tid not in seen:
                    seen.add(tid)
                    num_m = re.search(r"Test\s+(\d+)", a.get_text(strip=True))
                    num = int(num_m.group(1)) if num_m else None
                    links.append((tid, num, urljoin(BASE, a["href"])))
        return links
    except Exception as e:
        print(f"  index {section}: ERROR {e}", flush=True)
        return []


def parse_test_page(html, section):
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", {"name": "TEST"})
    if not form:
        return None, None, None, []
    title = form.find("input", {"name": "title"})
    title = title["value"] if title else ""
    passage_html = str(form)
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
    else:
        passage_div_html = ""
    if passage_div_html:
        passage_div_html = re.sub(
            r'src="(/[^"]+)"', lambda m: f'src="{BASE}{m.group(1)}"', passage_div_html)
    questions = {}
    for inp in form.find_all("input", {"type": "radio"}):
        qn = inp.get("name", "")
        if not qn.isdigit(): continue
        val = inp.get("value", "").strip()
        if not val: continue
        sib_txt = []
        for sib in inp.next_siblings:
            if getattr(sib, "name", None) == "input": break
            if hasattr(sib, "get_text"):
                t = sib.get_text(" ", strip=True)
            else:
                t = str(sib).strip()
            if t: sib_txt.append(t)
        opt_text = re.sub(r"^[A-J]\.\s*", "", " ".join(sib_txt).strip())
        questions.setdefault(int(qn), {})[val] = opt_text
    qlist = [{"q_num": qn, "options": questions[qn]} for qn in sorted(questions)]
    return title, passage_html, passage_div_html, qlist


def get_answer_key(test_id, section, q_nums):
    sorted_qs = sorted(q_nums)
    data = {
        "title": f"ACT {section.title()} practice test",
        "id": str(test_id),
        "type": section,
    }
    for i, q in enumerate(sorted_qs):
        data[str(q)] = "A" if i % 2 == 0 else "F"
    try:
        r = s.post(f"{BASE}/results.php", data=data,
                   headers={"Referer": f"{BASE}/act/{section}/test{test_id}.html"},
                   timeout=20)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")
        answers = {}
        pos = 0
        for tr in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) >= 3 and cells[0].isdigit():
                correct = cells[1].strip()
                if correct and len(correct) == 1 and correct in "ABCDEFGHIJK":
                    if pos < len(sorted_qs):
                        answers[sorted_qs[pos]] = correct
                pos += 1
        return answers
    except Exception:
        return {}


def scrape_test(conn, section, test_id, test_num, url):
    cur = conn.cursor()
    new_id = 20000 + test_id  # shift to avoid clashing with crackab id space
    cur.execute("SELECT 1 FROM tests WHERE id = ?", (new_id,))
    if cur.fetchone():
        return "skipped"
    r = s.get(url, timeout=20)
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    title, passage_html, passage_div_html, questions = parse_test_page(r.text, section)
    if not questions:
        return "no questions parsed"
    time.sleep(SLEEP)
    answers = get_answer_key(test_id, section, [q["q_num"] for q in questions])
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    extra_cols = ""
    extra_vals = ""
    if "passage_div_html" in cols:
        extra_cols = ", passage_div_html"
        extra_vals = ", ?"
    sql = f"""INSERT INTO tests (id, section, test_number, title, url, passage_html, source, scraped_at{extra_cols})
              VALUES (?,?,?,?,?,?,?,?{extra_vals})"""
    args = [new_id, section, test_num, title, url, passage_html, "actexam",
            time.strftime("%Y-%m-%dT%H:%M:%S")]
    if "passage_div_html" in cols:
        args.append(passage_div_html)
    cur.execute(sql, args)
    for q in questions:
        cur.execute(
            "INSERT OR REPLACE INTO questions (test_id, q_num, options_json, correct_answer) VALUES (?,?,?,?)",
            (new_id, q["q_num"], json.dumps(q["options"]), answers.get(q["q_num"]))
        )
    conn.commit()
    return f"OK ({len(questions)} q, {sum(1 for a in answers.values() if a)} answers)"


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    for section in ("english", "math", "reading", "science"):
        print(f"\n=== {section.upper()} ===", flush=True)
        tests = get_test_links(section)
        if not tests:
            continue
        print(f"  {len(tests)} tests discovered", flush=True)
        time.sleep(SLEEP)
        ok = 0
        for i, (tid, num, url) in enumerate(tests, 1):
            try:
                res = scrape_test(conn, section, tid, num, url)
                if res.startswith("OK"): ok += 1
                if i % 10 == 0 or i == len(tests):
                    print(f"  [{i:>3}/{len(tests)}] test{tid} → {res} (running OK: {ok})", flush=True)
            except Exception as e:
                print(f"  [{i}] test{tid} → ERROR {e}", flush=True)
            time.sleep(SLEEP)
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()
