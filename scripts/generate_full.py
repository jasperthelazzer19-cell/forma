"""
Generate one FULL ACT-style test using real PDFs as style references.

Fixes from previous version:
  - Section markers: CASE-SENSITIVE uppercase only (avoids TOC false matches)
  - Answer key: "Scoring Keys" plural at end of doc only
  - Per-passage chunking for English/Reading/Science (full counts)
  - Math: 2 calls of 30 questions each
  - Anthropic Sonnet primary, GPT-4o-mini fallback per section/passage

Goal: 75 English + 60 Math + 40 Reading + 40 Science = 215 questions.
Cost: ~$0.50-1.50.
"""
import json
import os
import re
import sqlite3
import sys
import time

import anthropic
import pdfplumber
from openai import OpenAI

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
PDF_DIR = "/Users/jasperlasser/actprep-crackab/official-pdfs"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o-mini"

with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    cred = f.read()
os.environ["ANTHROPIC_API_KEY"] = re.search(r"sk-ant-[a-zA-Z0-9_-]+", cred).group(0)
os.environ["OPENAI_API_KEY"] = next(
    c for c in re.findall(r"sk-(?:proj-|[a-zA-Z])[a-zA-Z0-9_-]{20,}", cred)
    if not c.startswith("sk-ant")
)
anth_client = anthropic.Anthropic()
openai_client = OpenAI()

# CASE-SENSITIVE uppercase only — section headers in the body are all-caps,
# while TOC mentions are mixed case ("Reading Test", "Mathematics Test").
SECTION_HEADERS = {
    "english": re.compile(r"\bENGLISH TEST\b"),
    "math":    re.compile(r"\bMATHEMATICS TEST\b"),
    "reading": re.compile(r"\bREADING TEST\b"),
    "science": re.compile(r"\bSCIENCE TEST\b"),
}
# "Scoring Keys" plural appears only in the actual answer section
ANSWER_KEY_RX = re.compile(r"Scoring Keys?\b|ANSWER KEY")


def get_reference_samples():
    """Pull one section sample (~5K chars) from 25MC1.pdf for each ACT section."""
    pdf_path = os.path.join(PDF_DIR, "25MC1.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        full = "\n".join(p.extract_text() or "" for p in pdf.pages)
    samples = {}
    section_positions = []
    for name, rx in SECTION_HEADERS.items():
        m = rx.search(full)
        if m:
            section_positions.append((m.start(), name))
    section_positions.sort()
    ak_iter = list(ANSWER_KEY_RX.finditer(full))
    ak_pos = ak_iter[-1].start() if ak_iter else len(full)  # last occurrence
    if section_positions and ak_pos < section_positions[-1][0]:
        ak_pos = len(full)  # fallback if AK match is before last section
    for i, (start, name) in enumerate(section_positions):
        end = section_positions[i + 1][0] if i + 1 < len(section_positions) else ak_pos
        section_text = full[start:end]
        samples[name] = section_text[:5000]
    return samples


# ── Per-passage prompts ────────────────────────────────────────────
ENG_PASSAGE_INSTR = """Generate ONE ORIGINAL ACT English passage + EXACTLY 15
questions. Passage ~400 words on a fresh topic (avoid the reference's topic).

Question mix for this passage:
  - 10 NO-CHANGE-style grammar/punctuation/word-choice questions
  - 3 rhetoric (best transition, tone, conciseness)
  - 2 macro (sentence/paragraph placement, add/delete)

Use A-D options on odd-numbered q, F-J on even.

Output ONLY JSON: {"passage":{"id":1,"title":"...","text":"..."},
  "questions":[{"q":1,"prompt":"... or null","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B","explanation":"..."}]}"""

READ_PASSAGE_INSTR = """Generate ONE ORIGINAL ACT Reading passage + 10 questions.
Passage type: {ptype}. ~750 words. Use a totally new topic (not the reference's).

Question mix: 3 main idea, 4 detail, 2 inference, 1 vocab-in-context.
A-D options on odd q, F-J on even.

Output ONLY JSON: {{"passage":{{"id":1,"title":"...","text":"..."}},
  "questions":[{{"q":1,"prompt":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"B","explanation":"..."}}]}}"""

SCI_PASSAGE_INSTR = """Generate ONE ORIGINAL ACT Science passage + {nq} questions.
Passage type: {ptype}. ~400 words with mock data tables/figures described in text
(e.g. "Table 1: temperature 20°C → reaction time 5.2s..."). Different topic from reference.

A-D options on odd q, F-J on even.

Output ONLY JSON: {{"passage":{{"id":1,"title":"...","text":"..."}},
  "questions":[{{"q":1,"prompt":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"B","explanation":"..."}}]}}"""

MATH_BATCH_INSTR = """Generate {nq} ORIGINAL ACT Math questions, q{q_start}-{q_end}
(difficulty {difficulty}). Topic distribution this batch:
  - {pa} Pre-Algebra
  - {ea} Elementary Algebra
  - {ia} Intermediate Algebra
  - {pg} Plane Geometry
  - {cg} Coordinate Geometry
  - {tr} Trigonometry

5 options each (A-E on odd q, F-K on even). For figures, describe in text.

Output ONLY JSON: {{"questions":[{{"q":{q_start},"topic":"...","prompt":"...",
  "options":{{"A":"...","B":"...","C":"...","D":"...","E":"..."}},"answer":"C","explanation":"..."}}]}}"""

READING_TYPES = ["Prose Fiction", "Social Science", "Humanities", "Natural Science"]
SCIENCE_PASSAGES = [
    ("Data Representation", 5),
    ("Data Representation", 5),
    ("Data Representation", 5),
    ("Research Summaries", 6),
    ("Research Summaries", 6),
    ("Conflicting Viewpoints", 7),
]


def build_user_prompt(section, ref, instr):
    return (f"REFERENCE (real ACT — match style/difficulty/voice but write "
            f"COMPLETELY NEW content, no reused topics, names, phrases):\n"
            f"--- BEGIN REFERENCE ---\n{ref}\n--- END REFERENCE ---\n\n"
            f"{instr}\n\nReturn only valid JSON, no markdown fences.")


def call_anth(prompt, max_tokens=8000):
    try:
        r = anth_client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=max_tokens,
            system="You write authentic ACT-style content. Output only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        out = r.content[0].text.strip()
        out = re.sub(r"^```(?:json)?\s*", "", out)
        out = re.sub(r"\s*```\s*$", "", out)
        cost = r.usage.input_tokens * 3 / 1_000_000 + r.usage.output_tokens * 15 / 1_000_000
        return json.loads(out), cost, "sonnet"
    except (json.JSONDecodeError, Exception) as e:
        msg = type(e).__name__ + ": " + str(e)[:160]
        return None, 0, msg


def call_openai(prompt, max_tokens=8000):
    try:
        r = openai_client.chat.completions.create(
            model=OPENAI_MODEL, max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You write authentic ACT-style content. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        out = r.choices[0].message.content
        cost = r.usage.prompt_tokens * 0.15 / 1_000_000 + r.usage.completion_tokens * 0.60 / 1_000_000
        return json.loads(out), cost, "gpt-4o-mini"
    except Exception as e:
        return None, 0, type(e).__name__ + ": " + str(e)[:160]


def generate_with_fallback(section, ref, instr, max_tokens=8000):
    """Try Sonnet first, fall back to OpenAI on any failure."""
    prompt = build_user_prompt(section, ref, instr)
    data, cost, model_or_err = call_anth(prompt, max_tokens)
    if data:
        return data, cost, model_or_err
    print(f"      sonnet failed ({model_or_err[:80]}) → openai", flush=True)
    data, cost2, model2 = call_openai(prompt, max_tokens)
    return data, cost + cost2, model2


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tests)")}
    for c, t, d in (("source","TEXT","DEFAULT 'crackab'"),
                    ("form_code","TEXT",""), ("year","INTEGER",""), ("month","TEXT","")):
        if c not in cols:
            conn.execute(f"ALTER TABLE tests ADD COLUMN {c} {t} {d}")
    conn.commit()


def next_id(conn):
    return conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()[0]


def insert_section(conn, form_code, section, passages, questions, model_used):
    tid = next_id(conn)
    title = f"{form_code} — {section.title()} (gen via {model_used})"
    parts = []
    for p in passages:
        if not p: continue
        ptext = (p.get("text") or "").strip()
        if ptext:
            ptitle = p.get("title") or f"Passage {p.get('id', '')}"
            parts.append(f"=== {ptitle} ===\n{ptext}")
    passage_text = "\n\n".join(parts)
    conn.execute("""INSERT INTO tests (id, section, test_number, title, url, source,
                    form_code, year, month, passage_text, scraped_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (tid, section, None, title, "generated", "generated",
                  form_code, 2026, "Generated", passage_text,
                  time.strftime("%Y-%m-%dT%H:%M:%S")))
    for q in questions:
        qnum = q.get("q")
        if qnum is None: continue
        opts = dict(q.get("options") or {})
        if q.get("prompt"): opts["_prompt"] = q["prompt"][:1500]
        if q.get("explanation"): opts["_explanation"] = q["explanation"][:800]
        conn.execute("""INSERT OR IGNORE INTO questions (test_id, q_num, options_json, correct_answer)
                        VALUES (?,?,?,?)""",
                     (tid, qnum, json.dumps(opts), q.get("answer")))
    conn.commit()
    return tid


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    print("=== reference samples ===", flush=True)
    samples = get_reference_samples()
    for k, v in samples.items():
        print(f"  {k}: {len(v)} chars", flush=True)
    if any(not samples.get(s) for s in ("english","math","reading","science")):
        print("MISSING SECTIONS — abort"); return
    # Auto-increment: GEN-001, GEN-002, ...
    row = conn.execute("SELECT form_code FROM tests WHERE form_code LIKE 'GEN-%' ORDER BY form_code DESC LIMIT 1").fetchone()
    if row:
        last_num = int(row[0].split("-")[1])
        form_code = f"GEN-{last_num + 1:03d}"
    else:
        form_code = "GEN-001"
    print(f"\n=== generating {form_code} ===\n", flush=True)
    total_cost = 0.0
    summary = {}

    # English — 5 passages × 15 questions, sequential offsets
    print("--- english (5 passages) ---", flush=True)
    eng_passages, eng_qs, models = [], [], []
    for i in range(1, 6):
        print(f"  passage {i}...", flush=True)
        data, cost, model = generate_with_fallback("english", samples["english"], ENG_PASSAGE_INSTR)
        total_cost += cost
        if not data:
            print(f"    failed", flush=True); continue
        p = data.get("passage") or {}
        p["id"] = i
        eng_passages.append(p)
        for q in data.get("questions", []):
            q["q"] = (i - 1) * 15 + q.get("q", 1)
            q["passage_id"] = i
            eng_qs.append(q)
        models.append(model)
        print(f"    ✓ {model}, ${cost:.3f}, +{len(data.get('questions',[]))} q", flush=True)
    if eng_qs:
        tid = insert_section(conn, form_code, "english", eng_passages, eng_qs, "/".join(set(models)))
        summary["english"] = len(eng_qs)
        print(f"  ✓ {len(eng_qs)} English questions, test_id={tid}\n", flush=True)

    # Math — 2 batches of 30
    print("--- math (2 batches of 30) ---", flush=True)
    math_qs, math_models = [], []
    batches = [
        (1, 30, "easier",
         dict(nq=30, pa=7, ea=5, ia=4, pg=7, cg=5, tr=2,
              q_start=1, q_end=30, difficulty="easier (q1-30)")),
        (31, 60, "harder",
         dict(nq=30, pa=7, ea=5, ia=5, pg=7, cg=4, tr=2,
              q_start=31, q_end=60, difficulty="harder (q31-60)")),
    ]
    for q_start, q_end, diff_label, kwargs in batches:
        print(f"  batch q{q_start}-q{q_end}...", flush=True)
        instr = MATH_BATCH_INSTR.format(**kwargs)
        data, cost, model = generate_with_fallback("math", samples["math"], instr, max_tokens=10000)
        total_cost += cost
        if not data:
            print(f"    failed", flush=True); continue
        for q in data.get("questions", []):
            qn = q.get("q", q_start)
            if qn < q_start or qn > q_end:
                continue
            math_qs.append(q)
        math_models.append(model)
        print(f"    ✓ {model}, ${cost:.3f}, +{len(data.get('questions',[]))} q", flush=True)
    if math_qs:
        tid = insert_section(conn, form_code, "math", [], math_qs, "/".join(set(math_models)))
        summary["math"] = len(math_qs)
        print(f"  ✓ {len(math_qs)} Math questions, test_id={tid}\n", flush=True)

    # Reading — 4 passages × 10
    print("--- reading (4 passages) ---", flush=True)
    rd_passages, rd_qs, rd_models = [], [], []
    for i, ptype in enumerate(READING_TYPES, 1):
        print(f"  passage {i} ({ptype})...", flush=True)
        instr = READ_PASSAGE_INSTR.format(ptype=ptype)
        data, cost, model = generate_with_fallback("reading", samples["reading"], instr)
        total_cost += cost
        if not data:
            print(f"    failed", flush=True); continue
        p = data.get("passage") or {}
        p["id"] = i
        rd_passages.append(p)
        for q in data.get("questions", []):
            q["q"] = (i - 1) * 10 + q.get("q", 1)
            q["passage_id"] = i
            rd_qs.append(q)
        rd_models.append(model)
        print(f"    ✓ {model}, ${cost:.3f}, +{len(data.get('questions',[]))} q", flush=True)
    if rd_qs:
        tid = insert_section(conn, form_code, "reading", rd_passages, rd_qs, "/".join(set(rd_models)))
        summary["reading"] = len(rd_qs)
        print(f"  ✓ {len(rd_qs)} Reading questions, test_id={tid}\n", flush=True)

    # Science — 6 passages
    print("--- science (6 passages) ---", flush=True)
    sc_passages, sc_qs, sc_models = [], [], []
    q_off = 0
    for i, (ptype, nq) in enumerate(SCIENCE_PASSAGES, 1):
        print(f"  passage {i} ({ptype}, {nq} q)...", flush=True)
        instr = SCI_PASSAGE_INSTR.format(ptype=ptype, nq=nq)
        data, cost, model = generate_with_fallback("science", samples["science"], instr)
        total_cost += cost
        if not data:
            print(f"    failed", flush=True); continue
        p = data.get("passage") or {}
        p["id"] = i
        sc_passages.append(p)
        for q in data.get("questions", []):
            q["q"] = q_off + q.get("q", 1)
            q["passage_id"] = i
            sc_qs.append(q)
        q_off += nq
        sc_models.append(model)
        print(f"    ✓ {model}, ${cost:.3f}, +{len(data.get('questions',[]))} q", flush=True)
    if sc_qs:
        tid = insert_section(conn, form_code, "science", sc_passages, sc_qs, "/".join(set(sc_models)))
        summary["science"] = len(sc_qs)
        print(f"  ✓ {len(sc_qs)} Science questions, test_id={tid}\n", flush=True)

    print(f"=== DONE — {form_code} ===", flush=True)
    print(f"  total cost: ${total_cost:.3f}", flush=True)
    for sec, n in summary.items():
        print(f"  {sec}: {n} questions", flush=True)


if __name__ == "__main__":
    main()
