"""
AI marker pass — insert [N] markers in the OCR'd passage at the right places.

Uses Claude Haiku (cheap) to read each test's passage_text + the 15 question
options, and return a copy of the passage with [1], [2], ... inserted inline
at each question's reference point. Saves to passage_text_marked.

Cost: ~$0.002 per test, ~$0.30-1 total for all English.
"""
import json
import os
import re
import sqlite3
import sys
import time

import anthropic

# Load API key from the vault file (per project memory)
CRED_PATH = "/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md"
DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
MODEL = "claude-haiku-4-5-20251001"

def get_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("ANTHROPIC_KEY"):
        return os.environ["ANTHROPIC_KEY"]
    with open(CRED_PATH) as f:
        m = re.search(r"sk-ant-[a-zA-Z0-9_-]+", f.read())
        if m:
            return m.group(0)
    sys.exit("No Anthropic key found")

os.environ["ANTHROPIC_API_KEY"] = get_key()
client = anthropic.Anthropic()

SYSTEM = """You re-render ACT English passages as HTML so they look like the
printed ACT format. The underlined portions stay underlined, with a small
subscript question-number right after the underline.

INPUT you receive:
  1. PASSAGE: OCR'd passage text. CRITICAL: the OCR captured the original
     printed subscript question-numbers as plain standalone digits (often on
     their own line, often right after the underlined phrase). For example a
     line containing just "12" usually means question 12's marker was right
     there in the printed passage.
  2. QUESTIONS: numbered multiple-choice options for each question (Q1..QN).
     Option A (or F) is usually "NO CHANGE" — the underlined text already
     matches the passage. Options B/C/D (or G/H/J) are alternative phrasings,
     which together hint at the length and shape of the underlined portion.

OUTPUT: the PASSAGE rendered as HTML, paragraphs in <p>...</p>, with each
underlined portion wrapped like this exact pattern:

    <u>{the underlined text}</u><sub>{question number}</sub>

CRITICAL RULES:
- Use the EXACT question numbers from the QUESTIONS section (1, 2, 3, ..., N
  for N total questions). NEVER invent other numbers. NEVER use 1051, 1052,
  global IDs, or anything other than the explicit Q1..QN range provided.
- **ORDERING IS STRICT**: the <sub>N</sub> markers MUST appear in ASCENDING
  ORDER in the passage. Q1 first, then Q2, then Q3, ..., never out of order.
  Real ACT passages are written so questions appear in document order. If
  you can't find Q5's underlined phrase before Q6's location, place Q5's
  marker at the latest plausible spot BEFORE Q6. Never insert Q11 between
  Q1 and Q2 — that's wrong by definition.
- When you see a standalone digit in the passage that matches one of the
  question numbers, treat it as a question-marker and REMOVE the standalone
  digit from the output (it gets replaced by <sub>N</sub>).
- The underlined phrase is the text immediately BEFORE the standalone digit.
  Use the question's answer options to determine exactly how much text is
  underlined (the length should be similar to options B/C/D).
- For questions about sentence order or adding/deleting sentences (no clear
  underlined phrase in the options), put just <sub>N</sub> at the plausible
  reference point (end of the relevant sentence/paragraph) — no <u> tags.
- For questions about the passage as a whole, append <sub>N</sub> at the end
  of the entire passage.
- Preserve every other word of the passage exactly. Only add <u>/<sub> tags
  and remove standalone digit markers.
- Output ONLY the HTML body. No markdown fences. No commentary. No JSON wrapper.

EXAMPLE INPUT:
PASSAGE:
The race was famously held in Hawaii
1
a beautiful place. Athletes from
all
2
the world come.

QUESTIONS:
Q1: A. NO CHANGE  B. Hawaii,  C. Hawaii, being  D. Hawaii, it is
Q2: F. NO CHANGE  G. across  H. throughout  J. over

EXAMPLE OUTPUT:
<p>The race was famously held in <u>Hawaii</u><sub>1</sub> a beautiful place. Athletes from <u>all</u><sub>2</sub> the world come.</p>"""

def mark_one(passage_text, questions):
    """questions is a list of (q_num, options_dict), passed in their stored order
    (which matches the visible 1..N numbering even when q_num itself is a
    global ID like 1051). Re-label as Q1..QN so the model uses simple numbers."""
    qlines = []
    for i, (q_num, opts) in enumerate(questions, 1):
        opt_str = "  ".join(f"{k}. {v}" for k, v in sorted(opts.items()))
        qlines.append(f"Q{i}: {opt_str}")
    qs_block = "\n".join(qlines)
    user = f"PASSAGE:\n{passage_text}\n\nQUESTIONS:\n{qs_block}"
    try:
        r = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        out = r.content[0].text.strip()
        # Strip stray markdown fences if the model wrapped its output
        out = re.sub(r"^```(?:html)?\s*", "", out)
        out = re.sub(r"\s*```$", "", out)
        return out.strip()
    except Exception as e:
        print(f"  API error: {e}", flush=True)
        return None

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, section, passage_text FROM tests
        WHERE (passage_text_marked IS NULL OR passage_text_marked = '')
          AND passage_text IS NOT NULL AND length(passage_text) >= 400
        ORDER BY CASE section WHEN 'english' THEN 1 WHEN 'reading' THEN 2 ELSE 3 END, id
    """).fetchall()
    print(f"{len(rows)} tests to mark", flush=True)
    ok = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        tid = row["id"]
        questions = conn.execute(
            "SELECT q_num, options_json FROM questions WHERE test_id = ? ORDER BY q_num",
            (tid,),
        ).fetchall()
        if not questions:
            continue
        qs = [(q["q_num"], json.loads(q["options_json"])) for q in questions]
        marked = mark_one(row["passage_text"], qs)
        if marked:
            conn.execute("UPDATE tests SET passage_text_marked = ? WHERE id = ?", (marked, tid))
            conn.commit()
            ok += 1
            if i % 5 == 0 or i == len(rows):
                elapsed = int(time.time() - t0)
                rate = i / max(1, elapsed)
                eta = int((len(rows) - i) / rate) if rate else 0
                print(f"  [{i:>3}/{len(rows)}] test{tid} ({row['section']}) → {len(marked)} chars · {elapsed}s, ~{eta//60}m{eta%60}s left", flush=True)
    print(f"DONE: {ok}/{len(rows)} marked", flush=True)

if __name__ == "__main__":
    main()
