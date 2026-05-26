"""
Generate one full ACT-style test, using REAL ACT passages from the
user's downloaded official PDFs as style references.

Approach:
  1. Pull section-specific text samples from the official PDFs as "style
     reference" exemplars (passages, question stems, option phrasing).
  2. Send to Claude Sonnet with: "Match this style/difficulty/tone exactly,
     but write completely original content. Don't reuse any wording."
  3. If Anthropic refuses (content filter), fall back to GPT-4o-mini.

Inserts result as source='generated' with form_code 'GEN-001'.
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

# Load both keys from vault
with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    cred_text = f.read()
anth_key = re.search(r"sk-ant-[a-zA-Z0-9_-]+", cred_text).group(0)
openai_key = next((c for c in re.findall(r"sk-(?:proj-|[a-zA-Z])[a-zA-Z0-9_-]{20,}", cred_text)
                   if not c.startswith("sk-ant")), None)
os.environ["ANTHROPIC_API_KEY"] = anth_key
os.environ["OPENAI_API_KEY"] = openai_key
anth_client = anthropic.Anthropic()
openai_client = OpenAI()


# ── Extract real reference text from official PDFs ───────────────
SECTION_HEADERS = {
    "english": re.compile(r"\bENGLISH TEST\b", re.I),
    "math":    re.compile(r"\bMATHEMATICS TEST\b", re.I),
    "reading": re.compile(r"\bREADING TEST\b", re.I),
    "science": re.compile(r"\bSCIENCE TEST\b", re.I),
}
ANSWER_KEY_RX = re.compile(r"Scoring Key|Answer Key|Key for", re.I)


def get_reference_samples():
    """Extract one passage + a few questions per section from 25MC1."""
    pdf_path = os.path.join(PDF_DIR, "25MC1.pdf")
    with pdfplumber.open(pdf_path) as pdf:
        full = "\n".join(p.extract_text() or "" for p in pdf.pages)
    samples = {}
    section_positions = []
    for name, rx in SECTION_HEADERS.items():
        m = rx.search(full)
        if m:
            section_positions.append((m.start(), name))
    ak = ANSWER_KEY_RX.search(full)
    ak_pos = ak.start() if ak else len(full)
    section_positions.sort()
    for i, (start, name) in enumerate(section_positions):
        end = section_positions[i + 1][0] if i + 1 < len(section_positions) else ak_pos
        section_text = full[start:end]
        # Limit to ~5K chars (1 passage + ~10 questions worth)
        samples[name] = section_text[:5000]
    return samples


SECTION_INSTRUCTIONS = {
    "english": """Generate a full ACT English section: 5 ORIGINAL passages
× 15 questions each = 75 questions total.

Each passage ~400 words, totally new topic. Question types per passage:
  - ~10 NO-CHANGE-style (grammar/punctuation/word choice)
  - ~3 rhetoric questions (best transition, tone)
  - ~2 macro questions (sentence/paragraph placement, add/delete)

Match the difficulty calibration and question shapes of the reference exactly,
but DO NOT REUSE any wording, names, places, topics, or scenarios from it.

A-D options on odd q, F-J on even.""",

    "math": """Generate a full ACT Math section: 60 ORIGINAL standalone questions,
easy → hard. Topic mix mirroring real ACT:
  - 14 Pre-Algebra, 10 Elementary Alg, 9 Intermediate Alg
  - 14 Plane Geo, 9 Coord Geo, 4 Trig

5 options each (A-E on odd, F-K on even). For figures, describe in text.
Match difficulty progression of the reference but use completely new scenarios,
numbers, and contexts.""",

    "reading": """Generate a full ACT Reading section: 4 ORIGINAL passages
× 10 questions each = 40 questions. Passage types IN ORDER:
  1. Prose Fiction (excerpt from a new original story)
  2. Social Science
  3. Humanities
  4. Natural Science

Each ~750 words. Question mix per passage: 3 main idea, 4 detail, 2 inference,
1 vocab-in-context. A-D on odd q, F-J on even.

Match the reference's tone and difficulty but use totally new topics, names,
and arguments.""",

    "science": """Generate a full ACT Science section: 6 ORIGINAL passages,
40 total questions. Format mix:
  - 3 Data Representation (5 q each)
  - 2 Research Summaries (6 q each)
  - 1 Conflicting Viewpoints (7 q, with 2-3 student/scientist views)

Each passage ~400 words with mock data tables/figures described in text. New
science topics (not the reference's). A-D on odd q, F-J on even.""",
}

JSON_SHAPES = {
    "english": """{"passages":[{"id":1,"title":"...","text":"..."}], "questions":[{"q":1,"passage_id":1,"prompt":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B","explanation":"..."}]}""",
    "math": """{"questions":[{"q":1,"topic":"Pre-Algebra","prompt":"...","options":{"A":"...","B":"...","C":"...","D":"...","E":"..."},"answer":"C","explanation":"..."}]}""",
    "reading": """{"passages":[{"id":1,"title":"...","text":"..."}], "questions":[{"q":1,"passage_id":1,"prompt":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B","explanation":"..."}]}""",
    "science": """{"passages":[{"id":1,"title":"...","text":"..."}], "questions":[{"q":1,"passage_id":1,"prompt":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"answer":"B","explanation":"..."}]}""",
}


def build_prompt(section, reference_text):
    return f"""Below is a REAL ACT {section} section excerpt as your STYLE REFERENCE.
You must produce content that matches its style, voice, difficulty calibration,
question phrasing patterns, and option-shape patterns — but with COMPLETELY
ORIGINAL content. Do NOT reuse any names, places, scenarios, topic specifics,
phrases, or sentences from the reference.

--- STYLE REFERENCE (do not reuse content) ---
{reference_text}
--- END REFERENCE ---

{SECTION_INSTRUCTIONS[section]}

Output ONLY valid JSON in this exact shape:
{JSON_SHAPES[section]}

No markdown fences. No commentary. Just JSON."""


def gen_with_anthropic(section, prompt):
    print(f"    trying Anthropic Sonnet...", flush=True)
    try:
        r = anth_client.messages.create(
            model=ANTHROPIC_MODEL, max_tokens=16000,
            system="You write authentic ACT-style content. Output only valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        out = r.content[0].text.strip()
        out = re.sub(r"^```(?:json)?\s*", "", out)
        out = re.sub(r"\s*```\s*$", "", out)
        cost = r.usage.input_tokens * 3 / 1_000_000 + r.usage.output_tokens * 15 / 1_000_000
        return json.loads(out), cost, "sonnet"
    except json.JSONDecodeError as e:
        print(f"    Sonnet JSON parse error: {e}", flush=True)
        return None, 0, None
    except Exception as e:
        msg = str(e)[:200]
        if "content" in msg.lower() or "policy" in msg.lower() or "blocked" in msg.lower():
            print(f"    Sonnet refused (content filter): {msg}", flush=True)
        else:
            print(f"    Sonnet error: {type(e).__name__}: {msg}", flush=True)
        return None, 0, None


def gen_with_openai(section, prompt):
    print(f"    falling back to OpenAI gpt-4o-mini...", flush=True)
    try:
        r = openai_client.chat.completions.create(
            model=OPENAI_MODEL, max_tokens=16000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You write authentic ACT-style content. Output only valid JSON, no fences."},
                {"role": "user", "content": prompt},
            ],
        )
        out = r.choices[0].message.content.strip()
        cost = r.usage.prompt_tokens * 0.15 / 1_000_000 + r.usage.completion_tokens * 0.60 / 1_000_000
        return json.loads(out), cost, "gpt-4o-mini"
    except Exception as e:
        print(f"    OpenAI error: {type(e).__name__}: {str(e)[:200]}", flush=True)
        return None, 0, None


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


def next_official_id(conn):
    row = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()
    return row[0]


def insert(conn, form_code, section, data, model_used):
    if not data or not data.get("questions"):
        return None
    tid = next_official_id(conn)
    title = f"{form_code} — {section.title()} (gen via {model_used})"
    parts = []
    for p in (data.get("passages") or []):
        ptext = (p.get("text") or "").strip()
        if ptext:
            ptitle = p.get("title") or f"Passage {p.get('id', '')}"
            parts.append(f"=== {ptitle} ===\n{ptext}")
    passage_text = "\n\n".join(parts)
    conn.execute("""
        INSERT INTO tests (id, section, test_number, title, url, source,
                           form_code, year, month, passage_text, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (tid, section, None, title, "generated", "generated",
          form_code, 2026, "Generated", passage_text,
          time.strftime("%Y-%m-%dT%H:%M:%S")))
    inserted = 0
    for q in data["questions"]:
        qnum = q.get("q")
        if qnum is None:
            continue
        opts = dict(q.get("options") or {})
        if q.get("prompt"):
            opts["_prompt"] = q["prompt"][:1500]
        if q.get("explanation"):
            opts["_explanation"] = q["explanation"][:800]
        conn.execute("""
            INSERT OR IGNORE INTO questions (test_id, q_num, options_json, correct_answer)
            VALUES (?,?,?,?)
        """, (tid, qnum, json.dumps(opts), q.get("answer")))
        inserted += 1
    conn.commit()
    return tid, inserted


def main():
    conn = sqlite3.connect(DB)
    ensure_schema(conn)
    print("=== loading reference samples from 25MC1.pdf ===", flush=True)
    samples = get_reference_samples()
    for k, v in samples.items():
        print(f"  {k}: {len(v)} chars reference", flush=True)
    form_code = "GEN-001"
    print(f"\n=== generating {form_code} ===\n", flush=True)
    total_cost = 0.0
    summary = []
    for section in ("english", "math", "reading", "science"):
        print(f"--- {section} ---", flush=True)
        ref = samples.get(section, "")
        if not ref:
            print(f"  no reference, skipping", flush=True)
            continue
        prompt = build_prompt(section, ref)
        t0 = time.time()
        data, cost, model = gen_with_anthropic(section, prompt)
        if not data:
            data, cost, model = gen_with_openai(section, prompt)
        elapsed = int(time.time() - t0)
        total_cost += cost
        if not data:
            print(f"  {section} BOTH models failed", flush=True)
            continue
        result = insert(conn, form_code, section, data, model)
        if result:
            tid, n = result
            print(f"  ✓ {section}: {n} questions, {elapsed}s, ${cost:.3f}, model={model}\n", flush=True)
            summary.append((section, n, model))
    print(f"=== DONE ===", flush=True)
    print(f"  total cost: ${total_cost:.3f}", flush=True)
    for sec, n, model in summary:
        print(f"  {sec}: {n} questions via {model}", flush=True)


if __name__ == "__main__":
    main()
