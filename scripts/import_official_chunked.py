"""
Chunked per-section OpenAI importer. Splits each PDF into 4 sections
(English/Math/Reading/Science) plus an answer-key chunk, then calls
gpt-4o-mini once per section so the output JSON fits in 16K tokens.

Result: full 215 questions per PDF instead of truncated 10-15%.
Cost: ~$0.20-0.50 total (24 calls × ~$0.01 each).
"""
import json
import os
import re
import sqlite3
import time

import pdfplumber
import requests
from openai import OpenAI

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
HERE = "/Users/jasperlasser/actprep-crackab"
PDF_CACHE = os.path.join(HERE, "official-pdfs")
os.makedirs(PDF_CACHE, exist_ok=True)

# Load OpenAI key from vault (skip Anthropic sk-ant)
with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    txt = f.read()
for cand in re.findall(r"sk-(?:proj-|[a-zA-Z])[a-zA-Z0-9_-]{20,}", txt):
    if not cand.startswith("sk-ant"):
        os.environ["OPENAI_API_KEY"] = cand
        break
client = OpenAI()
MODEL = "gpt-4o-mini"

PDFS = [
    ("25MC1",    2025, "Annual",  "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT.pdf"),
    ("25MC5",    2025, "Annual",  "https://www.act.org/content/dam/act/secured/documents/ACT-Test-Prep-ACT-Practice-Test-2-Form.pdf"),
    ("2176CPRE", 2024, "Annual",  "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-24-25.pdf"),
    ("74F",      2017, "April",   "https://mysatactprep.com/wp-content/uploads/2019/11/ACTPracticeTest2018-2019.pdf"),
    ("64E",      2007, "April",   "https://www.schs.cards/wp-content/uploads/2023/03/Test_1.pdf"),
    ("61C",      2006, "January", "https://www.schs.cards/wp-content/uploads/2023/03/Test_2.pdf"),
]

SECTION_HEADERS = [
    ("english", re.compile(r"\bENGLISH TEST\b", re.I)),
    ("math",    re.compile(r"\bMATHEMATICS TEST\b", re.I)),
    ("reading", re.compile(r"\bREADING TEST\b", re.I)),
    ("science", re.compile(r"\bSCIENCE TEST\b", re.I)),
]
ANSWER_KEY_RX = re.compile(r"Scoring Key|Answer Key|Key for", re.I)

SECTION_SYSTEM = {
    "english": """You parse one section of an ACT English test into JSON.
ACT English has 75 questions across 5 passages of ~15 questions each.
Output ONLY valid JSON, no markdown fences:
{
  "passages": [{"id": 1, "title": "...", "text": "<full passage>"}, ...],
  "questions": [
    {"q": 1, "passage_id": 1, "prompt": "<question text or null for NO CHANGE-style>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "..."}}, ...
  ]
}
For NO-CHANGE-style questions (where only the alternatives are shown), set prompt: null.
Preserve exact wording. Return every question you can identify in the input.""",

    "math": """You parse one section of an ACT Math test into JSON.
ACT Math has 60 standalone questions, each with 5 options (A-E alternating with F-K).
Output ONLY valid JSON, no markdown fences:
{
  "questions": [
    {"q": 1, "prompt": "<full question text>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, ...
  ]
}
Preserve exact wording. No passages array for math.""",

    "reading": """You parse one section of an ACT Reading test into JSON.
ACT Reading has 4 passages, 10 questions each (40 total).
Output ONLY valid JSON, no markdown fences:
{
  "passages": [{"id": 1, "title": "...", "text": "<full passage>"}, ...],
  "questions": [
    {"q": 1, "passage_id": 1, "prompt": "<question>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "..."}}, ...
  ]
}
Preserve exact wording.""",

    "science": """You parse one section of an ACT Science test into JSON.
ACT Science has 6-7 passages with charts/data, 40 questions total.
Output ONLY valid JSON, no markdown fences:
{
  "passages": [{"id": 1, "title": "...", "text": "<passage including descriptions of tables/figures>"}, ...],
  "questions": [
    {"q": 1, "passage_id": 1, "prompt": "<question>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "..."}}, ...
  ]
}
Preserve exact wording.""",
}


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    if "source" not in cols:
        conn.execute("ALTER TABLE tests ADD COLUMN source TEXT DEFAULT 'crackab'")
    if "form_code" not in cols:
        conn.execute("ALTER TABLE tests ADD COLUMN form_code TEXT")
    if "year" not in cols:
        conn.execute("ALTER TABLE tests ADD COLUMN year INTEGER")
    if "month" not in cols:
        conn.execute("ALTER TABLE tests ADD COLUMN month TEXT")
    conn.commit()


def download(form_code, url):
    p = os.path.join(PDF_CACHE, f"{form_code}.pdf")
    if os.path.exists(p) and os.path.getsize(p) > 50000:
        return p
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None
    with open(p, "wb") as f:
        f.write(r.content)
    return p


def extract_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def split_sections(text):
    """Return dict section -> text chunk + 'answers' chunk."""
    starts = []
    for name, rx in SECTION_HEADERS:
        m = rx.search(text)
        if m:
            starts.append((m.start(), name))
    ak = ANSWER_KEY_RX.search(text)
    ak_pos = ak.start() if ak else len(text)
    starts.sort()
    out = {}
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else ak_pos
        out[name] = text[pos:end]
    out["__answers__"] = text[ak_pos:] if ak else ""
    return out


def parse_answer_key(ans_text, section):
    """Best-effort answer-key parser. Returns dict q_num -> letter for the
    given section's expected question range."""
    ranges = {"english": (1, 75), "math": (1, 60),
              "reading": (1, 40), "science": (1, 40)}
    lo, hi = ranges[section]
    # Try inline N.X pattern first
    answers = {}
    # Pattern: "1. B  2. F  3. A ..." or "1)B 2)F" etc.
    for m in re.finditer(r"(\d{1,3})\s*[.\)]\s*([A-K])\b", ans_text):
        q, letter = int(m.group(1)), m.group(2)
        if lo <= q <= hi and letter in "ABCDEFGHJK" and q not in answers:
            answers[q] = letter
    return answers


def structure_section(section_name, section_text, form_code):
    if len(section_text) < 200:
        return None
    # Trim wildly long sections to fit context window
    if len(section_text) > 100_000:
        section_text = section_text[:100_000]
    try:
        r = client.chat.completions.create(
            model=MODEL,
            max_tokens=16384,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SECTION_SYSTEM[section_name]},
                {"role": "user", "content": f"FORM CODE: {form_code} · SECTION: {section_name.upper()}\n\n--- SECTION TEXT ---\n{section_text}"},
            ],
        )
        out = r.choices[0].message.content
        return json.loads(out)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}", flush=True)
        return None
    except Exception as e:
        print(f"    API error: {type(e).__name__}: {str(e)[:200]}", flush=True)
        return None


def next_official_id(conn):
    row = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()
    return row[0]


def insert_section(conn, form_code, year, month, pdf_url, section, sec_data, answers):
    if not sec_data or not sec_data.get("questions"):
        return None, 0
    tid = next_official_id(conn)
    title = f"Form {form_code} ({month} {year}) — {section.title()}"
    passages = sec_data.get("passages", []) or []
    parts = []
    for p in passages:
        ptext = (p.get("text") or "").strip()
        if ptext:
            ptitle = p.get("title") or f"Passage {p.get('id', '')}"
            parts.append(f"=== {ptitle} ===\n{ptext}")
    passage_text = "\n\n".join(parts)
    conn.execute("""
        INSERT INTO tests (id, section, test_number, title, url, source,
                           form_code, year, month, passage_text, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (tid, section, None, title, pdf_url, "official", form_code, year, month,
          passage_text, time.strftime("%Y-%m-%dT%H:%M:%S")))
    inserted = 0
    for q in sec_data.get("questions", []):
        qnum = q.get("q")
        if qnum is None:
            continue
        opts = dict(q.get("options") or {})
        prompt = q.get("prompt")
        if prompt:
            opts["_prompt"] = prompt[:600]
        ans = answers.get(qnum) or q.get("answer")
        try:
            conn.execute("""
                INSERT OR IGNORE INTO questions (test_id, q_num, options_json, correct_answer)
                VALUES (?,?,?,?)
            """, (tid, qnum, json.dumps(opts), ans))
            inserted += 1
        except Exception as e:
            print(f"      skip q{qnum}: {e}", flush=True)
    conn.commit()
    return tid, inserted


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    print(f"=== chunked OpenAI import: {len(PDFS)} PDFs × 4 sections ===\n", flush=True)
    t_start = time.time()
    summary = []
    for form_code, year, month, pdf_url in PDFS:
        print(f"--- {form_code} ({month} {year}) ---", flush=True)
        path = download(form_code, pdf_url)
        if not path:
            print(f"  download FAILED", flush=True)
            continue
        text = extract_text(path)
        if len(text) < 5000:
            print(f"  too little text - image-based PDF, skipping", flush=True)
            continue
        sections = split_sections(text)
        ans_text = sections.get("__answers__", "")
        form_total_q = 0
        form_total_a = 0
        for sec_name in ("english", "math", "reading", "science"):
            sec_text = sections.get(sec_name)
            if not sec_text:
                print(f"  {sec_name}: section marker not found", flush=True)
                continue
            print(f"  {sec_name}: structuring {len(sec_text)} chars...", flush=True)
            t0 = time.time()
            data = structure_section(sec_name, sec_text, form_code)
            if not data:
                print(f"  {sec_name}: structuring failed", flush=True)
                continue
            answers = parse_answer_key(ans_text, sec_name)
            tid, n = insert_section(conn, form_code, year, month, pdf_url,
                                    sec_name, data, answers)
            ans_count = sum(1 for q in data.get("questions", [])
                            if answers.get(q.get("q")) or q.get("answer"))
            n_pas = len(data.get("passages", []) or [])
            print(f"    → test_id={tid}, {n} questions, {ans_count} answers, "
                  f"{n_pas} passages · {int(time.time()-t0)}s", flush=True)
            form_total_q += n
            form_total_a += ans_count
        summary.append((form_code, form_total_q, form_total_a))
        print(f"  TOTAL: {form_total_q} questions, {form_total_a} answers\n", flush=True)
    elapsed = int(time.time() - t_start)
    print(f"=== DONE in {elapsed//60}m{elapsed%60}s ===", flush=True)
    for fc, q, a in summary:
        print(f"  {fc}: {q} questions, {a} answers", flush=True)


if __name__ == "__main__":
    main()
