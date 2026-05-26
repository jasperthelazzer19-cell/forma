"""
Scrape Varsity Tutors ACT "Learn by Concept" question banks.

Data lives in static HTML — Next.js Flight payload pushes a stringified
JSON containing { questions: [{ answers:[{text,isCorrect}], explanation, ...}] }.
We curl each topic page, parse the payload, save to crackab.db with source='varsity'.

Sections: english / math / reading / science
Per section: ~10-20 "Learn by Concept" topics, each with ~5-20 pages × 10 q

ID space: starts at 30000 to avoid clashing with crackab (1-9999), official
(10000-19999), actexam (20000-29999 reserved).
"""
import json
import re
import sqlite3
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.varsitytutors.com"
DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 1.2
ID_OFFSET = 30000

SECTION_SLUGS = {
    "english": "act-english",
    "math": "act-math",
    "reading": "act-reading",
    "science": "act-science",
}

s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept": "text/html"})


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    for c, t, d in (("source", "TEXT", "DEFAULT 'crackab'"),
                    ("topic", "TEXT", "")):
        if c not in cols:
            conn.execute(f"ALTER TABLE tests ADD COLUMN {c} {t} {d}")
    qcols = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    if "topic" not in qcols:
        conn.execute("ALTER TABLE questions ADD COLUMN topic TEXT")
    conn.commit()


def get_topics(section):
    """Hit /practice/subjects/<slug>/help/ to find topic links."""
    url = f"{BASE}/practice/subjects/{SECTION_SLUGS[section]}"
    r = s.get(url, timeout=15)
    if r.status_code != 200:
        return []
    # links look like /practice/subjects/act-english/help/<topic-slug>
    pat = re.compile(rf'/practice/subjects/{SECTION_SLUGS[section]}/help/([a-z0-9-]+)')
    return sorted(set(pat.findall(r.text)))


def get_total_pages(html):
    """Parse 'Page X of Y' (rendered as part of payload as either text or JSON)."""
    m = re.search(r'Page\\?\\?\s*\d+\s+of\s+(\d+)', html)
    if not m:
        m = re.search(r'"pagination":\s*{[^}]*"total":\s*(\d+)', html)
    return int(m.group(1)) if m else 1


def extract_payload_questions(html):
    """Extract questions[] array from __next_f.push payload."""
    # The payload is structured: __next_f.push([1, "JSON_STRING"])
    # JSON_STRING contains \"questions\":[...] somewhere inside, with all
    # quotes escaped (\"). Find the literal substring after we JS-decode.
    pushes = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', html)
    questions = []
    topic = None
    for push in pushes:
        # JS string literal → JSON-ready string. Scan left-to-right: every
        # backslash escape consumes the next char. `\\` → `\`, `\"` → `"`.
        # Other escapes (`\n`, `\uXXXX`, `\/`) pass through for json.loads.
        out = []
        i = 0
        L = len(push)
        while i < L:
            ch = push[i]
            if ch == '\\' and i + 1 < L:
                nxt = push[i+1]
                if nxt == '\\':
                    out.append('\\'); i += 2; continue
                if nxt == '"':
                    out.append('"'); i += 2; continue
                out.append(ch + nxt); i += 2; continue
            out.append(ch); i += 1
        decoded = ''.join(out)
        # Find "pathString" → that's the topic slug
        tm = re.search(r'"pathString":"([^"]+)"', decoded)
        if tm and not topic:
            topic = tm.group(1)
        # Find the start of "questions":[
        idx = decoded.find('"questions":[')
        if idx < 0:
            continue
        start = idx + len('"questions":')
        # Walk forward to find balanced ]
        depth = 0
        i = start
        in_str = False
        esc = False
        while i < len(decoded):
            ch = decoded[i]
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if ch == '[': depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        try:
                            arr = json.loads(decoded[start:i+1])
                            questions.extend(arr)
                        except Exception as e:
                            print(f"  parse err: {e}", flush=True)
                        break
            i += 1
    return topic, questions


def normalize_question(q, topic, section, ord_in_page):
    """Convert Varsity question dict → our schema row."""
    answers = q.get("answers") or []
    if not answers:
        return None
    # Letter assignment: position in `answers` array, A/F per section convention
    base_letter = "F" if section in ("math",) else "A"
    base_letter = "A"  # keep A-D for all — simpler
    if section == "math":
        # ACT math uses A-E for odd Q and F-K for even Q.
        # Varsity arrays are typically 4 (English/Read/Sci) or 5 (Math).
        # We'll just use A-E for math.
        letters = ["A", "B", "C", "D", "E"]
    else:
        # English/Reading/Science use A/B/C/D (and F/G/H/J for even questions).
        # We use A-D uniformly for storage; display layer can re-letter if wanted.
        letters = ["A", "B", "C", "D"]
    opts = {}
    correct = None
    for i, a in enumerate(answers):
        if i >= len(letters):
            break
        L = letters[i]
        opts[L] = a.get("text", "")
        if a.get("isCorrect"):
            correct = L
    # Stem & passage live separately — Varsity has "questionParts" or just "text"
    stem = q.get("text") or q.get("question") or ""
    # Some Varsity questions have a "passage" or "context" field
    passage = q.get("passage") or q.get("context") or ""
    explanation = q.get("explanation") or ""
    if stem:
        opts["_prompt"] = stem[:2000]
    if explanation:
        opts["_explanation"] = explanation[:3000]
    return {
        "options_json": json.dumps(opts, ensure_ascii=False),
        "correct_answer": correct,
        "passage_text": passage,
        "topic": topic,
    }


def fetch_topic_pages(section, topic_slug):
    """One HTTP GET returns ALL questions for a topic in the Next.js payload."""
    url = f"{BASE}/practice/subjects/{SECTION_SLUGS[section]}/help/{topic_slug}"
    r = s.get(url, timeout=20)
    if r.status_code != 200:
        return []
    topic, qs = extract_payload_questions(r.text)
    return [(1, topic, qs)]


def insert_topic(conn, section, topic_slug, pages_data):
    """Bundle all questions in a topic into one 'test' row, store individual q's."""
    if not any(p[2] for p in pages_data):
        return 0
    cur = conn.cursor()
    # Allocate a test_id: ID_OFFSET + section_offset + hash-ish topic id
    sec_off = {"english": 0, "math": 5000, "reading": 10000, "science": 15000}[section]
    # Use topic position within the section for stable IDs
    cur.execute("SELECT COUNT(*) FROM tests WHERE source='varsity' AND section=?", (section,))
    n_existing = cur.fetchone()[0]
    tid = ID_OFFSET + sec_off + n_existing + 1
    # Insert test row
    title = f"Varsity Tutors — {topic_slug.replace('-', ' ').title()}"
    cur.execute("""INSERT OR REPLACE INTO tests
                   (id, section, source, topic, title, url, scraped_at, test_number)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (tid, section, "varsity", topic_slug, title,
                 f"{BASE}/practice/subjects/{SECTION_SLUGS[section]}/help/{topic_slug}",
                 time.strftime("%Y-%m-%dT%H:%M:%S"), None))
    inserted = 0
    q_num = 1
    for page, page_topic, raw_qs in pages_data:
        for q in raw_qs:
            norm = normalize_question(q, page_topic or topic_slug, section, q_num)
            if not norm:
                continue
            try:
                cur.execute("""INSERT OR REPLACE INTO questions
                               (test_id, q_num, options_json, correct_answer, topic)
                               VALUES (?,?,?,?,?)""",
                            (tid, q_num, norm["options_json"],
                             norm["correct_answer"], norm["topic"]))
                inserted += 1
                q_num += 1
            except Exception as e:
                print(f"  insert err q{q_num}: {e}", flush=True)
    conn.commit()
    return inserted


def main():
    sections = sys.argv[1:] or list(SECTION_SLUGS.keys())
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    grand_total = 0
    for section in sections:
        if section not in SECTION_SLUGS:
            print(f"skip unknown section: {section}", flush=True)
            continue
        print(f"\n=== {section.upper()} ===", flush=True)
        topics = get_topics(section)
        print(f"  discovered {len(topics)} topics: {', '.join(topics[:5])}{'...' if len(topics) > 5 else ''}", flush=True)
        time.sleep(SLEEP)
        sec_total = 0
        for topic in topics:
            try:
                pages = fetch_topic_pages(section, topic)
                n = insert_topic(conn, section, topic, pages)
                print(f"  ✓ {topic}: {n} q saved", flush=True)
                sec_total += n
            except Exception as e:
                print(f"  ✗ {topic}: {type(e).__name__}: {str(e)[:140]}", flush=True)
            time.sleep(SLEEP)
        print(f"  → {section}: {sec_total} questions total", flush=True)
        grand_total += sec_total
    print(f"\n=== DONE: {grand_total} questions across {len(sections)} sections ===", flush=True)


if __name__ == "__main__":
    main()
