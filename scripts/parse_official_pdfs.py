"""
Pure-regex parser for official ACT PDFs. No AI in the loop.

Extracts:
  - Section text (English, Math, Reading, Science)
  - Numbered questions + their multiple-choice options
  - Correct answers from the Scoring Key section

Inserts into the existing crackab.db with source='official'.
"""
import json
import os
import re
import sqlite3
import time

import pdfplumber
import requests

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
HERE = "/Users/jasperlasser/actprep-crackab"
PDF_CACHE = os.path.join(HERE, "official-pdfs")
os.makedirs(PDF_CACHE, exist_ok=True)

# (form_code, year, month, source_url, pdf_url)
PDFS = [
    ("25MC1",    2025, "Annual",   "act.org",          "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT.pdf"),
    ("25MC5",    2025, "Annual",   "act.org",          "https://www.act.org/content/dam/act/secured/documents/ACT-Test-Prep-ACT-Practice-Test-2-Form.pdf"),
    ("2176CPRE", 2024, "Annual",   "act.org",          "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-24-25.pdf"),
    ("74F",      2017, "April",    "mysatactprep.com", "https://mysatactprep.com/wp-content/uploads/2019/11/ACTPracticeTest2018-2019.pdf"),
    ("64E",      2007, "April",    "schs.cards",       "https://www.schs.cards/wp-content/uploads/2023/03/Test_1.pdf"),
    ("61C",      2006, "January",  "schs.cards",       "https://www.schs.cards/wp-content/uploads/2023/03/Test_2.pdf"),
]

SECTION_HEADERS = [
    ("english", re.compile(r"\bENGLISH TEST\b", re.I)),
    ("math",    re.compile(r"\bMATHEMATICS TEST\b", re.I)),
    ("reading", re.compile(r"\bREADING TEST\b", re.I)),
    ("science", re.compile(r"\bSCIENCE TEST\b", re.I)),
]
ANSWER_KEY_HEADER = re.compile(r"Scoring Key|Answer Key|Key for", re.I)


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    if "source"    not in cols: conn.execute("ALTER TABLE tests ADD COLUMN source TEXT DEFAULT 'crackab'")
    if "form_code" not in cols: conn.execute("ALTER TABLE tests ADD COLUMN form_code TEXT")
    if "year"      not in cols: conn.execute("ALTER TABLE tests ADD COLUMN year INTEGER")
    if "month"     not in cols: conn.execute("ALTER TABLE tests ADD COLUMN month TEXT")
    conn.commit()


def download_pdf(form_code, url):
    path = os.path.join(PDF_CACHE, f"{form_code}.pdf")
    if os.path.exists(path) and os.path.getsize(path) > 50000:
        return path
    print(f"  downloading {form_code}…", flush=True)
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None
    with open(path, "wb") as f: f.write(r.content)
    return path


def extract_full_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def split_sections(text):
    """Return dict section_name -> text_chunk for each section + 'answers' chunk."""
    # Find positions of each section marker
    section_starts = []
    for name, rx in SECTION_HEADERS:
        m = rx.search(text)
        if m: section_starts.append((m.start(), name))
    # Find answer key start
    ak = ANSWER_KEY_HEADER.search(text)
    ak_pos = ak.start() if ak else len(text)
    # Sort by position
    section_starts.sort()
    sections = {}
    for i, (pos, name) in enumerate(section_starts):
        end = section_starts[i+1][0] if i+1 < len(section_starts) else ak_pos
        sections[name] = text[pos:end]
    sections["__answers__"] = text[ak_pos:] if ak else ""
    return sections


# ── Question parsing ──────────────────────────────────────────────
# Numbered questions: "1." followed by anything, until next "2." at line start
QUESTION_SPLIT = re.compile(r"(?ms)(?:^|\n)\s*(\d{1,3})\.\s+(.*?)(?=(?:\n\s*\d{1,3}\.\s)|\Z)")
# Options: A-J letter + period, captures option text up to next option or question
OPTION_SPLIT = re.compile(r"(?ms)(?:^|\n)\s*([A-K])\.\s+(.*?)(?=(?:\n\s*[A-K]\.\s)|\Z)")


def parse_questions(section_text):
    """Return list of {q_num, prompt, options}. Dedups on q_num (keeps first).
    Also drops false positives — must have >=2 multiple-choice options."""
    out = []
    seen = set()
    matches = list(QUESTION_SPLIT.finditer(section_text))
    for m in matches:
        qnum = int(m.group(1))
        if qnum in seen or qnum < 1 or qnum > 75:
            continue
        body = m.group(2).strip()
        opt_iter = list(OPTION_SPLIT.finditer(body))
        if not opt_iter:
            continue
        first_opt_start = opt_iter[0].start()
        prompt = body[:first_opt_start].strip()
        options = {}
        for om in opt_iter:
            letter = om.group(1)
            opt_text = re.sub(r"\s+", " ", om.group(2).strip())
            options[letter] = opt_text[:400]
        if len(options) >= 2:
            seen.add(qnum)
            out.append({"q_num": qnum, "prompt": prompt, "options": options})
    return out


# ── Answer key parsing ────────────────────────────────────────────
# Answer tables look like: "1. B  2. F  3. A  4. G ..."
ANSWER_INLINE = re.compile(r"(\d{1,3})\.\s*([A-K])")


def parse_answer_key(answer_text):
    """Return dict {q_num: letter}. Best-effort, takes the first 4 'banks' it finds."""
    # Try inline pattern first
    answers = {}
    for m in ANSWER_INLINE.finditer(answer_text):
        qnum, letter = int(m.group(1)), m.group(2)
        if qnum not in answers and 1 <= qnum <= 75 and letter in "ABCDEFGHJK":
            answers[qnum] = letter
    return answers


def section_answer_range(section):
    return {"english": (1, 75), "math": (1, 60), "reading": (1, 40), "science": (1, 40)}[section]


def slice_answers(all_answers, section):
    lo, hi = section_answer_range(section)
    return {q: all_answers[q] for q in all_answers if lo <= q <= hi}


def next_official_id(conn):
    row = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()
    return row[0]


def insert_section(conn, form_code, year, month, pdf_url, section, section_text, questions, answers):
    if not questions:
        return None
    tid = next_official_id(conn)
    title = f"Form {form_code} ({month} {year}) — {section.title()}"
    # Strip the "scoring key" tail if it accidentally got into the section text
    body = section_text
    ak = ANSWER_KEY_HEADER.search(body)
    if ak: body = body[:ak.start()]
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    conn.execute("""
        INSERT INTO tests (id, section, test_number, title, url, source,
                           form_code, year, month, passage_text, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (tid, section, None, title, pdf_url, "official", form_code, year, month,
          body, time.strftime("%Y-%m-%dT%H:%M:%S")))
    for q in questions:
        opts = q["options"]
        if q["prompt"]:
            opts = {**opts, "_prompt": q["prompt"][:400]}
        conn.execute("""
            INSERT OR IGNORE INTO questions (test_id, q_num, options_json, correct_answer)
            VALUES (?,?,?,?)
        """, (tid, q["q_num"], json.dumps(opts), answers.get(q["q_num"])))
    conn.commit()
    return tid


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    print(f"=== importing {len(PDFS)} official ACT PDFs (no AI) ===", flush=True)
    summary = []
    for form_code, year, month, source, pdf_url in PDFS:
        print(f"\n--- {form_code} ({month} {year}) ---", flush=True)
        existing = conn.execute(
            "SELECT COUNT(*) FROM tests WHERE source='official' AND form_code=?",
            (form_code,)
        ).fetchone()[0]
        if existing:
            print(f"  already imported ({existing} sections), skipping", flush=True)
            continue
        path = download_pdf(form_code, pdf_url)
        if not path:
            print(f"  download FAILED")
            continue
        text = extract_full_text(path)
        if len(text) < 5000:
            print(f"  too little text ({len(text)} chars) — image-based PDF, skipping")
            continue
        sections = split_sections(text)
        ans_text = sections.get("__answers__", "")
        all_answers = parse_answer_key(ans_text)
        print(f"  answer key: {len(all_answers)} answers parsed", flush=True)
        for sec_name in ("english", "math", "reading", "science"):
            sec_text = sections.get(sec_name)
            if not sec_text:
                print(f"  {sec_name}: section not found", flush=True)
                continue
            qs = parse_questions(sec_text)
            sec_answers = slice_answers(all_answers, sec_name)
            tid = insert_section(conn, form_code, year, month, pdf_url,
                                 sec_name, sec_text, qs, sec_answers)
            print(f"  {sec_name}: test_id={tid}, {len(qs)} questions, {len(sec_answers)} answers",
                  flush=True)
        summary.append(form_code)
    print(f"\n=== DONE — {len(summary)} PDFs imported ===", flush=True)


if __name__ == "__main__":
    main()
