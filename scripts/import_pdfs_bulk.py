"""
Bulk-import all PDFs from official-pdfs/{crackab,tutor,github}/ into the DB.

Reuses import_official_v2's per-section pipeline (gpt-4o-mini, format-aware).
Skips PDFs whose form_code is already imported.
"""
import glob
import json
import os
import re
import sqlite3
import sys
import time
import traceback

import pdfplumber

# Reuse parsing helpers from existing import script
from import_official_v2 import (
    ensure_schema, extract_text, split_sections, parse_answers,
    call_ai, chunk_section, TARGETS, SECTION_HEADERS, ANSWER_KEY_RX,
)
from ocr_pdf import ocr_pdf

OCR_MIN_CHARS = 5000  # if pdfplumber yields less, fall back to OCR
OCR_MAX_PAGES = 120   # cap OCR work per PDF (a real ACT booklet is ~80-100 pgs)

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
DIRS = [
    "/Users/jasperlasser/actprep-crackab/official-pdfs/crackab",
    "/Users/jasperlasser/actprep-crackab/official-pdfs/tutor",
    "/Users/jasperlasser/actprep-crackab/official-pdfs/github",
]
MIN_SIZE_KB = 500  # skip answer-key fragments


def parse_filename(path):
    """Extract (form_code, year, month, fmt) from any of the file naming
    conventions we have:
      crackab-0012-ACT_2008_Form_61B.pdf
      ACT 201704 Form 74F.pdf
      tutela-74C-2017dec.pdf
      satprep-1572CPRE-15-16.pdf
      focusonlearning-74FPRE-19-20.pdf
      schs-71C-2012-2013.pdf
    Returns dict or None if can't parse.
    """
    name = os.path.basename(path)
    base = name.replace(".pdf", "")
    # Try patterns in order of specificity
    # 1. "ACT 201704 Form 74F" or "ACT_2008_Form_61B"
    m = re.search(r'ACT[_ ](\d{4})(\d{2})?[_ ]?Form[_ ]+([A-Z0-9]+)', base, re.I)
    if m:
        y = int(m.group(1))
        mo = m.group(2) or ""
        return {"form_code": m.group(3).upper(), "year": y, "month": mo, "fmt": "new" if y >= 2025 else "old"}
    # 1b. "ACT_Month_YYYY_Form_XXX" (crackab style: ACT_May_2002_Form_55C)
    m = re.search(r'ACT_(January|February|March|April|May|June|July|August|September|October|November|December)_(\d{4})_Form_([A-Z0-9]+)', base, re.I)
    if m:
        y = int(m.group(2))
        return {"form_code": m.group(3).upper(), "year": y, "month": m.group(1), "fmt": "new" if y >= 2025 else "old"}
    # 2. "ACT_YYYY_Form_XXX" (underscores)
    m = re.search(r'ACT_(\d{4})_Form_([A-Z0-9]+)', base, re.I)
    if m:
        y = int(m.group(1))
        return {"form_code": m.group(2).upper(), "year": y, "month": "", "fmt": "new" if y >= 2025 else "old"}
    # 3. "tutela-74C-2017dec" / "schs-71C-2012-2013"
    m = re.search(r'(?:tutela|schs|satprep|focusonlearning|edisonprep)-([A-Z0-9]+)-(\d{2,4})', base, re.I)
    if m:
        code = m.group(1).upper()
        ystr = m.group(2)
        y = int(ystr) if len(ystr) == 4 else 2000 + int(ystr)
        return {"form_code": code, "year": y, "month": "", "fmt": "new" if y >= 2025 else "old"}
    # 4. Generic fallback: find any ##F/##C/A##/B##/C##/D##/E##/F##/G##/H##/J##/Z## token
    m = re.search(r'\b(\d{2}MC\d|\d{4}[A-Z]+|[A-Z]\d{2}|\d{2}[A-Z])\b', base)
    if m:
        # Use file mtime year as fallback
        y = 2020
        return {"form_code": m.group(1).upper(), "year": y, "month": "", "fmt": "old"}
    return None


def already_imported(conn, form_code):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tests WHERE source='official' AND form_code=?", (form_code,))
    return cur.fetchone()[0] > 0


def import_one_pdf(conn, path, meta):
    """Parse a single PDF into per-section test rows. Returns total questions inserted."""
    try:
        text = extract_text(path)
    except Exception as e:
        print(f"  pdf err: {e}", flush=True)
        text = ""
    # Fallback to OCR when pdfplumber returns too little (scanned PDFs)
    if len(text) < OCR_MIN_CHARS:
        try:
            ocr_path = ocr_pdf(path, max_pages=OCR_MAX_PAGES)
            ocr_text = open(ocr_path).read()
            if len(ocr_text) > len(text):
                print(f"  OCR rescued: {len(text)} → {len(ocr_text)} chars", flush=True)
                text = ocr_text
        except Exception as e:
            print(f"  OCR err: {type(e).__name__}: {str(e)[:120]}", flush=True)
    if len(text) < 2000:
        print(f"  still too little text ({len(text)} chars), skip", flush=True)
        return 0, 0.0
    sections = split_sections(text)
    ans_text = sections.get("__answers__", "")
    targets = TARGETS[meta["fmt"]]
    total = 0
    grand_cost = 0.0
    for sec_name in ("english", "math", "reading", "science"):
        sec_text = sections.get(sec_name)
        target = targets[sec_name]
        if target == 0 or not sec_text:
            continue
        n_chunks = 1 if target <= 20 else (2 if target <= 40 else 3)
        chunks = chunk_section(sec_text, n_chunks) if n_chunks > 1 else [sec_text]
        all_questions = []
        all_passages = []
        sec_cost = 0.0
        for i, ch in enumerate(chunks, 1):
            data, cost = call_ai(sec_name, ch)
            sec_cost += cost
            if data:
                all_questions.extend(data.get("questions") or [])
                all_passages.extend(data.get("passages") or [])
        # Dedup questions by q_num
        seen = set()
        deduped = []
        for q in all_questions:
            qn = q.get("q")
            if qn is None or qn in seen: continue
            seen.add(qn)
            deduped.append(q)
        if not deduped:
            continue
        # Insert test row
        tid = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()[0]
        title = f"Form {meta['form_code']} ({meta['month']} {meta['year']}) — {sec_name.title()}".strip()
        parts = []
        for p in all_passages:
            pt = (p.get("text") or "").strip()
            if pt:
                parts.append(f"=== {p.get('title') or 'Passage'} ===\n{pt}")
        passage_text = "\n\n".join(parts)
        conn.execute("""INSERT INTO tests (id, section, test_number, title, url, source,
                        form_code, year, month, passage_text, scraped_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                     (tid, sec_name, None, title, path, "official",
                      meta["form_code"], meta["year"], meta["month"],
                      passage_text, time.strftime("%Y-%m-%dT%H:%M:%S")))
        ans_map = parse_answers(ans_text, sec_name, target)
        sec_inserted = 0
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
                sec_inserted += 1
            except Exception:
                pass
        conn.commit()
        total += sec_inserted
        grand_cost += sec_cost
        ans_count = sum(1 for q in conn.execute(
            "SELECT correct_answer FROM questions WHERE test_id=?", (tid,)
        ) if q[0])
        print(f"    {sec_name}: {sec_inserted}q / {ans_count} ans / ${sec_cost:.3f}", flush=True)
    return total, grand_cost


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    pdfs = []
    for d in DIRS:
        for path in sorted(glob.glob(os.path.join(d, "*.pdf"))):
            sz_kb = os.path.getsize(path) // 1024
            if sz_kb < MIN_SIZE_KB:
                continue
            meta = parse_filename(path)
            if not meta:
                continue
            pdfs.append((path, meta, sz_kb))
    print(f"=== {len(pdfs)} PDFs eligible ===", flush=True)
    # Dedup against already-imported form_codes
    new_pdfs = [(p, m, sz) for p, m, sz in pdfs if not already_imported(conn, m["form_code"])]
    print(f"=== {len(new_pdfs)} new (after skipping duplicates) ===", flush=True)
    if "--dry-run" in sys.argv:
        for p, m, sz in new_pdfs[:20]:
            print(f"  would import: {m['form_code']} ({m['month']} {m['year']}, {m['fmt']}, {sz}KB) ← {os.path.basename(p)}")
        return
    grand_total = 0
    grand_cost = 0.0
    failures = 0
    for i, (path, meta, sz) in enumerate(new_pdfs, 1):
        print(f"\n[{i}/{len(new_pdfs)}] {meta['form_code']} ({meta['year']}, {sz}KB) — {os.path.basename(path)[:60]}", flush=True)
        try:
            t, c = import_one_pdf(conn, path, meta)
            grand_total += t
            grand_cost += c
            print(f"  → +{t}q (running total: {grand_total}q, ${grand_cost:.2f})", flush=True)
        except Exception as e:
            failures += 1
            print(f"  EXCEPT: {type(e).__name__}: {str(e)[:200]}", flush=True)
            traceback.print_exc()
    print(f"\n=== DONE: {grand_total} questions imported, ${grand_cost:.2f} spent, {failures} failures ===", flush=True)


if __name__ == "__main__":
    main()
