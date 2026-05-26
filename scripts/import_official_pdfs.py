"""
Download + parse the 11 known official ACT PDFs, AI-structure each into
sections + questions + answers, insert into the DB with source='official'.

Adds:
  - tests.source column ('crackab' default | 'official')
  - tests.form_code column
  - tests.year column

Each PDF becomes 4 sub-tests (one per section: English/Math/Reading/Science).
Math/Science answers parsed from the answer key at the end. Passage text
extracted directly (no OCR needed — these PDFs have selectable text).
"""
import json
import os
import re
import sqlite3
import sys
import time
from urllib.parse import urlparse

import pdfplumber
import requests
import anthropic

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
HERE = "/Users/jasperlasser/actprep-crackab"
PDF_CACHE = os.path.join(HERE, "official-pdfs")
os.makedirs(PDF_CACHE, exist_ok=True)

with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    os.environ["ANTHROPIC_API_KEY"] = re.search(r"sk-ant-[a-zA-Z0-9_-]+", f.read()).group(0)
client = anthropic.Anthropic()
MODEL = "claude-haiku-4-5-20251001"

# ── PDFs to import (form_code, year, month, source_url, pdf_url) ──
PDFS = [
    ("25MC1",    2025, "Annual",   "act.org",           "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT.pdf"),
    ("25MC5",    2025, "Annual",   "act.org",           "https://www.act.org/content/dam/act/secured/documents/ACT-Test-Prep-ACT-Practice-Test-2-Form.pdf"),
    ("2176CPRE", 2024, "Annual",   "act.org",           "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-24-25.pdf"),
    ("PFTA-ES",  2025, "Annual",   "act.org",           "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-Spanish.pdf"),
    ("74F",      2017, "April",    "mysatactprep.com",  "https://mysatactprep.com/wp-content/uploads/2019/11/ACTPracticeTest2018-2019.pdf"),
    ("64E",      2007, "April",    "schs.cards",        "https://www.schs.cards/wp-content/uploads/2023/03/Test_1.pdf"),
    ("61C",      2006, "January",  "schs.cards",        "https://www.schs.cards/wp-content/uploads/2023/03/Test_2.pdf"),
    # Google Drive ones — drive URLs need conversion to direct download
    # ("72CPRE-DRIVE", 2017, "Annual", "piqosity",   "https://drive.google.com/uc?export=download&id=1hBc2wdW_ZUChsDu_YO7lYym4verktG02"),
    # ("74FPRE-DRIVE", 2020, "Annual", "piqosity",   "https://drive.google.com/uc?export=download&id=1oYlQ-xf32BQLsyVS5G4iuuxx2GZLoMXN"),
    # ("2176CPRE-DRIVE", 2024, "Annual", "piqosity", "https://drive.google.com/uc?export=download&id=1x7dZRGm7M3txlByS04XlQ-rQ4R8_FepL"),
]


def ensure_schema():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cols = {r[1] for r in cur.execute("PRAGMA table_info(tests)")}
    if "source" not in cols:
        cur.execute("ALTER TABLE tests ADD COLUMN source TEXT DEFAULT 'crackab'")
    if "form_code" not in cols:
        cur.execute("ALTER TABLE tests ADD COLUMN form_code TEXT")
    if "year" not in cols:
        cur.execute("ALTER TABLE tests ADD COLUMN year INTEGER")
    if "month" not in cols:
        cur.execute("ALTER TABLE tests ADD COLUMN month TEXT")
    conn.commit()
    conn.close()


def download_pdf(form_code, url):
    name = f"{form_code}.pdf"
    path = os.path.join(PDF_CACHE, name)
    if os.path.exists(path) and os.path.getsize(path) > 50000:
        return path
    print(f"  downloading {form_code}...", flush=True)
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}", flush=True)
        return None
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def extract_text(pdf_path):
    """Return list of (page_num, text) for each page."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            pages.append((i, txt))
    return pages


# ── AI structurer ──────────────────────────────────────────────────
STRUCTURE_SYSTEM = """You receive raw text extracted from an official ACT
practice test PDF. Your job: identify the four sections (English, Math,
Reading, Science) and the answer key at the end, then return a JSON object
with this exact shape:

{
  "english": {
    "passages": [{"id": 1, "text": "...passage text..."}, ...],
    "questions": [
      {"q": 1, "passage_id": 1, "prompt": "...question text or null for NO CHANGE-type...",
       "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
       "answer": "B"},
      ...
    ]
  },
  "math":    { "questions": [...] },   // math has no passages, 60 standalone questions
  "reading": { "passages": [...], "questions": [...] },  // 4 passages, 10 q each
  "science": { "passages": [...], "questions": [...] }   // 6-7 passages w/ data
}

Rules:
- Only include sections you found in the text. Skip missing/incomplete ones.
- Answers MUST come from the answer key (look for a table mapping question
  numbers to letters). If no answer key exists, set "answer" to null.
- For ENGLISH, attach each question to its passage_id. If a question is
  "NO CHANGE" style with no prompt, set prompt: null.
- Preserve exact wording in options.
- Output ONLY the JSON object. No markdown fences. No commentary."""


def structure_with_ai(form_code, text):
    """Send the full extracted PDF text to Haiku, get structured JSON back."""
    # Trim insanely long inputs — full ACT PDF text fits in ~60-80K tokens
    if len(text) > 200_000:
        text = text[:200_000]
    try:
        r = client.messages.create(
            model=MODEL,
            max_tokens=16384,
            system=STRUCTURE_SYSTEM,
            messages=[{"role": "user", "content": f"FORM CODE: {form_code}\n\n--- PDF TEXT ---\n{text}"}],
        )
        out = r.content[0].text.strip()
        out = re.sub(r"^```(?:json)?\s*", "", out)
        out = re.sub(r"\s*```$", "", out)
        return json.loads(out)
    except json.JSONDecodeError as e:
        print(f"  JSON parse failed: {e}", flush=True)
        return None
    except Exception as e:
        print(f"  AI error: {e}", flush=True)
        return None


def next_official_test_id(conn):
    """Reserve a fresh test_id in the 10000+ range so we don't clash with crackab."""
    row = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()
    return row[0]


def insert_test(conn, form_code, year, month, source_url, pdf_url, section, structured_section):
    """Insert one section as a test in the DB."""
    if not structured_section or not structured_section.get("questions"):
        return None
    tid = next_official_test_id(conn)
    title = f"Form {form_code} ({month} {year}) — {section.title()}"

    # Build passage_text from passages
    passages = structured_section.get("passages", [])
    passage_text = ""
    if passages:
        parts = []
        for p in passages:
            ptext = p.get("text", "").strip()
            if ptext:
                parts.append(f"=== Passage {p.get('id', '')} ===\n{ptext}")
        passage_text = "\n\n".join(parts)

    conn.execute("""
        INSERT INTO tests (id, section, test_number, title, url, source,
                           form_code, year, month, passage_text, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (tid, section, None, title, source_url, "official", form_code, year, month,
          passage_text, time.strftime("%Y-%m-%dT%H:%M:%S")))

    # Insert questions
    for q in structured_section.get("questions", []):
        qnum = q.get("q")
        if qnum is None:
            continue
        opts = q.get("options", {})
        ans = q.get("answer")
        prompt = q.get("prompt") or ""
        # Store prompt in options as a special key for now; keep schema simple
        opts_with_prompt = {**opts, "_prompt": prompt} if prompt else opts
        conn.execute("""
            INSERT INTO questions (test_id, q_num, options_json, correct_answer)
            VALUES (?,?,?,?)
        """, (tid, qnum, json.dumps(opts_with_prompt), ans))
    conn.commit()
    return tid


def main():
    ensure_schema()
    conn = sqlite3.connect(DB)
    print(f"=== importing {len(PDFS)} official ACT PDFs ===\n", flush=True)
    summary = []
    for form_code, year, month, source, pdf_url in PDFS:
        print(f"\n--- {form_code} ({month} {year}) ---", flush=True)
        # Skip if already imported
        existing = conn.execute(
            "SELECT COUNT(*) FROM tests WHERE source='official' AND form_code=?",
            (form_code,)
        ).fetchone()[0]
        if existing:
            print(f"  already imported ({existing} sections), skipping", flush=True)
            continue
        path = download_pdf(form_code, pdf_url)
        if not path:
            print(f"  DOWNLOAD FAILED", flush=True)
            continue
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"  pdf: {size_mb:.1f} MB", flush=True)
        pages = extract_text(path)
        full_text = "\n\n".join(t for _, t in pages)
        print(f"  text: {len(full_text)} chars from {len(pages)} pages", flush=True)
        if len(full_text) < 5000:
            print(f"  too little text — probably image-based PDF, needs OCR (skipping)", flush=True)
            continue
        struct = structure_with_ai(form_code, full_text)
        if not struct:
            print(f"  AI structuring failed", flush=True)
            continue
        added = {}
        for section in ("english", "math", "reading", "science"):
            sec_data = struct.get(section)
            if not sec_data:
                continue
            tid = insert_test(conn, form_code, year, month, pdf_url, pdf_url, section, sec_data)
            if tid:
                qcount = len(sec_data.get("questions", []))
                added[section] = (tid, qcount)
        for sec, (tid, qc) in added.items():
            print(f"  {sec}: test_id={tid}, {qc} questions", flush=True)
        summary.append((form_code, added))

    print(f"\n=== DONE — {len(summary)} PDFs imported ===", flush=True)
    for fc, added in summary:
        secs = ", ".join(f"{s}({qc})" for s, (_, qc) in added.items())
        print(f"  {fc}: {secs}", flush=True)


if __name__ == "__main__":
    main()
