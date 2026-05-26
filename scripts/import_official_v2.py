"""
Per-section, properly-sized re-import of official ACT PDFs using gpt-4o-mini.

Targets match the actual ACT format per year:
  - 2025+ (new): English 50, Math 45, Reading 36, Science (optional, skip)
  - pre-2025:   English 75, Math 60, Reading 40, Science 40

For sections >30 questions, chunks further by passage to fit output tokens.
"""
import json
import os
import re
import sqlite3
import sys
import time

import pdfplumber
from openai import OpenAI

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
PDF_DIR = "/Users/jasperlasser/actprep-crackab/official-pdfs"

with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    txt = f.read()
for cand in re.findall(r"sk-(?:proj-|[a-zA-Z])[a-zA-Z0-9_-]{20,}", txt):
    if not cand.startswith("sk-ant"):
        os.environ["OPENAI_API_KEY"] = cand
        break
client = OpenAI()
MODEL = "gpt-4o-mini"

# (form_code, year, month, format)
# format: "new" = 2025+ ACT (50/45/36/0), "old" = pre-2025 (75/60/40/40)
PDFS = [
    ("25MC1",    2025, "Annual",  "new"),
    ("25MC5",    2025, "Annual",  "new"),
    ("2176CPRE", 2024, "Annual",  "old"),
    ("74F",      2017, "April",   "old"),
    ("64E",      2007, "April",   "old"),
    ("61C",      2006, "January", "old"),
]

TARGETS = {
    "new": {"english": 50, "math": 45, "reading": 36, "science": 0},
    "old": {"english": 75, "math": 60, "reading": 40, "science": 40},
}

SECTION_HEADERS = {
    "english": re.compile(r"\bENGLISH TEST\b"),
    "math":    re.compile(r"\bMATHEMATICS TEST\b"),
    "reading": re.compile(r"\bREADING TEST\b"),
    "science": re.compile(r"\bSCIENCE TEST\b"),
}
ANSWER_KEY_RX = re.compile(r"Scoring Keys?\b|ANSWER KEY")


SECTION_SYSTEM = {
    "english": """Parse this ACT English section excerpt into JSON. Extract EVERY
question + every option you can find. Output JSON only:
{"passages":[{"id":1,"title":"...","text":"..."}], "questions":[{"q":1,"passage_id":1,"prompt":"... or null","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B"}]}""",
    "math": """Parse this ACT Math section excerpt into JSON. Extract EVERY
question + every option. Math has 5 options (A-E or F-K). Output JSON only:
{"questions":[{"q":1,"prompt":"...","options":{"A":"...","B":"...","C":"...","D":"...","E":"..."},"answer":"C"}]}""",
    "reading": """Parse this ACT Reading section excerpt into JSON. Extract EVERY
question + every option. Output JSON only:
{"passages":[{"id":1,"title":"...","text":"..."}], "questions":[{"q":1,"passage_id":1,"prompt":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B"}]}""",
    "science": """Parse this ACT Science section excerpt into JSON. Extract EVERY
question + every option. Output JSON only:
{"passages":[{"id":1,"title":"...","text":"..."}], "questions":[{"q":1,"passage_id":1,"prompt":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B"}]}""",
}


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    for c, t, d in (("source","TEXT","DEFAULT 'crackab'"),
                    ("form_code","TEXT",""), ("year","INTEGER",""), ("month","TEXT","")):
        if c not in cols:
            conn.execute(f"ALTER TABLE tests ADD COLUMN {c} {t} {d}")
    conn.commit()


def extract_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def split_sections(text):
    starts = []
    for name, rx in SECTION_HEADERS.items():
        m = rx.search(text)
        if m: starts.append((m.start(), name))
    ak = list(ANSWER_KEY_RX.finditer(text))
    ak_pos = ak[-1].start() if ak else len(text)
    starts.sort()
    if starts and ak_pos < starts[-1][0]:
        ak_pos = len(text)
    out = {}
    for i, (start, name) in enumerate(starts):
        end = starts[i+1][0] if i+1 < len(starts) else ak_pos
        out[name] = text[start:end]
    out["__answers__"] = text[ak_pos:] if ak else ""
    return out


def parse_answers(ans_text, section, target):
    answers = {}
    for m in re.finditer(r"(\d{1,3})\s*[.\)]\s*([A-K])\b", ans_text):
        q, l = int(m.group(1)), m.group(2)
        if 1 <= q <= target and l in "ABCDEFGHJK" and q not in answers:
            answers[q] = l
    return answers


def call_ai(section, chunk_text, max_tokens=14000):
    try:
        r = client.chat.completions.create(
            model=MODEL, max_tokens=max_tokens,
            response_format={"type": "json_object"},
            timeout=90,  # hard timeout — hung calls now error out instead of stalling forever
            messages=[
                {"role": "system", "content": SECTION_SYSTEM[section]},
                {"role": "user", "content": chunk_text},
            ],
        )
        cost = r.usage.prompt_tokens * 0.15/1e6 + r.usage.completion_tokens * 0.60/1e6
        return json.loads(r.choices[0].message.content), cost
    except json.JSONDecodeError as e:
        print(f"    JSON err: {e}", flush=True)
        return None, 0
    except Exception as e:
        print(f"    API err: {type(e).__name__}: {str(e)[:160]}", flush=True)
        return None, 0


def chunk_section(section_text, n_chunks):
    """Split into n_chunks roughly-equal byte chunks (passage boundaries
    aren't reliable across PDF layouts)."""
    L = len(section_text)
    return [section_text[i*L//n_chunks : (i+1)*L//n_chunks] for i in range(n_chunks)]


def import_section(conn, form_code, year, month, pdf_url, section, sec_text,
                   ans_text, target):
    if target == 0:
        return None, 0
    if not sec_text or target <= 0:
        return None, 0
    # Decide chunking based on target size
    n_chunks = 1 if target <= 20 else (2 if target <= 40 else 3)
    chunks = chunk_section(sec_text, n_chunks) if n_chunks > 1 else [sec_text]
    print(f"    {section}: {len(sec_text)} chars, {n_chunks} chunk(s), target {target} q", flush=True)
    all_passages = []
    all_questions = []
    total_cost = 0.0
    for i, ch in enumerate(chunks, 1):
        data, cost = call_ai(section, ch)
        total_cost += cost
        if not data:
            continue
        for p in (data.get("passages") or []):
            all_passages.append(p)
        for q in (data.get("questions") or []):
            all_questions.append(q)
        print(f"      chunk {i}/{n_chunks}: +{len(data.get('questions') or [])} q, ${cost:.3f}", flush=True)
    # Dedupe questions by q_num (keep first occurrence)
    seen = set()
    deduped = []
    for q in all_questions:
        qn = q.get("q")
        if qn is None or qn in seen: continue
        seen.add(qn)
        deduped.append(q)
    # Merge in answers from answer key
    ans_map = parse_answers(ans_text, section, target)
    # Insert
    tid = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()[0]
    title = f"Form {form_code} ({month} {year}) — {section.title()}"
    parts = []
    for p in all_passages:
        ptext = (p.get("text") or "").strip()
        if ptext:
            ptitle = p.get("title") or f"Passage {p.get('id','')}"
            parts.append(f"=== {ptitle} ===\n{ptext}")
    passage_text = "\n\n".join(parts)
    conn.execute("""INSERT INTO tests (id, section, test_number, title, url, source,
                    form_code, year, month, passage_text, scraped_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (tid, section, None, title, pdf_url, "official",
                  form_code, year, month, passage_text,
                  time.strftime("%Y-%m-%dT%H:%M:%S")))
    inserted = 0
    for q in deduped:
        qn = q.get("q")
        if qn is None: continue
        opts = dict(q.get("options") or {})
        if q.get("prompt"): opts["_prompt"] = q["prompt"][:1500]
        ans = ans_map.get(qn) or q.get("answer")
        try:
            conn.execute("""INSERT OR IGNORE INTO questions
                            (test_id, q_num, options_json, correct_answer)
                            VALUES (?,?,?,?)""",
                         (tid, qn, json.dumps(opts), ans))
            inserted += 1
        except Exception:
            pass
    conn.commit()
    return tid, inserted, total_cost


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    # Wipe old official imports for a clean slate
    conn.execute("DELETE FROM questions WHERE test_id IN (SELECT id FROM tests WHERE source='official')")
    conn.execute("DELETE FROM tests WHERE source='official'")
    conn.commit()
    print(f"=== re-importing {len(PDFS)} official PDFs (full per-section) ===\n", flush=True)
    grand_cost = 0.0
    summary = []
    for form_code, year, month, fmt in PDFS:
        print(f"--- {form_code} ({month} {year}) — {fmt} ACT ---", flush=True)
        path = os.path.join(PDF_DIR, f"{form_code}.pdf")
        if not os.path.exists(path):
            print("  PDF missing, skip"); continue
        text = extract_text(path)
        if len(text) < 5000:
            print(f"  too little text ({len(text)} chars), skip"); continue
        sections = split_sections(text)
        ans_text = sections.get("__answers__", "")
        targets = TARGETS[fmt]
        form_total = 0
        for sec_name in ("english", "math", "reading", "science"):
            sec_text = sections.get(sec_name)
            target = targets[sec_name]
            if target == 0:
                continue
            if not sec_text:
                print(f"  {sec_name}: section header not found in PDF"); continue
            result = import_section(conn, form_code, year, month, path,
                                    sec_name, sec_text, ans_text, target)
            if result is None or len(result) < 3:
                continue
            tid, n, cost = result
            grand_cost += cost
            form_total += n
            ans_count = sum(1 for q in conn.execute(
                "SELECT correct_answer FROM questions WHERE test_id=?", (tid,)
            ) if q[0])
            print(f"      ✓ test_id={tid}, {n} q, {ans_count} answers, ${cost:.3f}",
                  flush=True)
        summary.append((form_code, form_total))
        print(f"  TOTAL: {form_total} q across sections\n", flush=True)
    print(f"=== DONE — ${grand_cost:.3f} ===", flush=True)
    for fc, n in summary:
        print(f"  {fc}: {n} questions", flush=True)


if __name__ == "__main__":
    main()
