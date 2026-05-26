"""
Generate one full ACT-style practice test using Claude Sonnet.

Produces 4 sections (English, Math, Reading, Science) totaling ~215 questions
of fully original ACT-style material. No copyright issue — content is freshly
generated, modeled on ACT's format/difficulty calibration but with new
passages, scenarios, and questions.

Inserts into the DB as source='generated' with form_code like 'GEN-001'.
"""
import json
import os
import re
import sqlite3
import sys
import time

import anthropic

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
MODEL = "claude-sonnet-4-6"

with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    os.environ["ANTHROPIC_API_KEY"] = re.search(r"sk-ant-[a-zA-Z0-9_-]+", f.read()).group(0)
client = anthropic.Anthropic()


SECTION_PROMPTS = {
    "english": """Generate a full ACT English section: 5 ORIGINAL passages
covering different topics (e.g. a personal narrative, a profile of a person/
place, a history/social-studies piece, a science/tech piece, an arts/culture
piece). 15 questions per passage = 75 total questions.

Each passage should be ~400 words and include underlined portions/insertion
points that the questions reference. Mix of question types per passage:
  - ~10 NO-CHANGE-style questions (grammar/punctuation/word choice/conciseness)
  - ~3 rhetoric questions (best word for tone, transition choice)
  - ~2 macro-level questions (sentence/paragraph placement, add/delete sentence)

Output ONLY valid JSON in this exact shape:
{
  "passages": [
    {"id": 1, "title": "...", "text": "<full ~400-word passage text>"}
  ],
  "questions": [
    {"q": 1, "passage_id": 1, "prompt": "<question text, or null for NO-CHANGE-style>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
     "answer": "B",
     "explanation": "<1-2 sentence explanation>"}
  ]
}

Use A-D options on odd-numbered questions, F-J on even (matching real ACT).
Difficulty distribution: 40% easy, 40% medium, 20% hard.""",

    "math": """Generate a full ACT Math section: 60 ORIGINAL standalone questions,
ordered easy → hard. Topic distribution mirrors the real ACT:
  - Pre-Algebra: 14 questions
  - Elementary Algebra: 10
  - Intermediate Algebra: 9
  - Plane Geometry: 14
  - Coordinate Geometry: 9
  - Trigonometry: 4

Each question has 5 options (A-E on odd q, F-K on even). Difficulty progression:
q1-20 easy, q21-40 medium, q41-60 hard.

Output ONLY valid JSON:
{
  "questions": [
    {"q": 1, "topic": "Pre-Algebra", "prompt": "<full question, include geometry
     diagrams described in text like 'In the figure below, ABC is a right
     triangle with the right angle at B, AB = 3, BC = 4...'>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."},
     "answer": "C",
     "explanation": "<1-2 sentence solution>"}
  ]
}

For questions that reference figures, describe the figure clearly in the prompt
text (lengths, angles, coordinates). No need for actual images.""",

    "reading": """Generate a full ACT Reading section: 4 ORIGINAL passages × 10
questions = 40 total. Passage types in this exact order:
  1. Prose Fiction (excerpt from an original short story)
  2. Social Science (history/economics/sociology, expository)
  3. Humanities (essay on art/music/literature/philosophy)
  4. Natural Science (biology/physics/chemistry/earth science)

Each passage ~750 words. Question mix per passage:
  - 3 main idea / author's purpose
  - 4 detail / specific reference
  - 2 inference / reasoning
  - 1 vocabulary-in-context

Output ONLY valid JSON:
{
  "passages": [
    {"id": 1, "title": "<title>",
     "text": "<full ~750-word passage>"}
  ],
  "questions": [
    {"q": 1, "passage_id": 1,
     "prompt": "<question text>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
     "answer": "B",
     "explanation": "<1-2 sentence explanation>"}
  ]
}

A-D options on odd q, F-J on even. Difficulty: 30% easy, 50% medium, 20% hard.""",

    "science": """Generate a full ACT Science section: 6 ORIGINAL passages,
each with mock data tables/figures described in text. 40 total questions.

Passage format distribution:
  - 3 Data Representation (1 passage: 5 q each = 15 q)
  - 2 Research Summaries (2 passages: 6 q each = 12 q)
  - 1 Conflicting Viewpoints (1 passage: 7 q with 2-3 student/scientist hypotheses)

Each passage describes an experimental setup, includes 1-3 mock tables or
figures (in text, like: "Table 1 shows the reaction time at temperatures
20°C: 5.2s, 30°C: 3.8s, 40°C: 2.9s, 50°C: 2.1s"), and is ~400 words.

Output ONLY valid JSON:
{
  "passages": [
    {"id": 1, "title": "<topic>",
     "text": "<passage with mock data clearly written out>"}
  ],
  "questions": [
    {"q": 1, "passage_id": 1,
     "prompt": "<question that requires data interpretation>",
     "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
     "answer": "C",
     "explanation": "<1-2 sentence explanation>"}
  ]
}

Topics should be realistic intro-college science (biology, chemistry, physics,
earth science, environmental). A-D on odd q, F-J on even.""",
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


def generate_section(section_name):
    print(f"  generating {section_name}...", flush=True)
    t0 = time.time()
    r = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system="You are an ACT test writer. Generate authentic ACT-style content. Output ONLY valid JSON, no markdown fences, no commentary.",
        messages=[{"role": "user", "content": SECTION_PROMPTS[section_name]}],
    )
    out = r.content[0].text.strip()
    out = re.sub(r"^```(?:json)?\s*", "", out)
    out = re.sub(r"\s*```\s*$", "", out)
    elapsed = int(time.time() - t0)
    in_toks = r.usage.input_tokens
    out_toks = r.usage.output_tokens
    cost = in_toks * 3 / 1_000_000 + out_toks * 15 / 1_000_000
    print(f"    → {elapsed}s, {in_toks} in / {out_toks} out tokens, ~${cost:.3f}", flush=True)
    try:
        return json.loads(out), cost
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}", flush=True)
        # Save raw for inspection
        with open(f"/tmp/gen_{section_name}_raw.txt", "w") as f:
            f.write(out)
        return None, cost


def next_official_id(conn):
    row = conn.execute("SELECT COALESCE(MAX(id), 9999) + 1 FROM tests WHERE id >= 10000").fetchone()
    return row[0]


def next_gen_form_code(conn):
    row = conn.execute("""
        SELECT form_code FROM tests
        WHERE form_code LIKE 'GEN-%'
        ORDER BY form_code DESC LIMIT 1
    """).fetchone()
    if not row:
        return "GEN-001"
    last_num = int(row[0].split("-")[1])
    return f"GEN-{last_num + 1:03d}"


def insert_section(conn, form_code, section, data):
    if not data or not data.get("questions"):
        return None
    tid = next_official_id(conn)
    title = f"{form_code} — {section.title()} (AI-generated, Sonnet)"
    passages = data.get("passages", []) or []
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
            opts["_prompt"] = q["prompt"][:1200]
        if q.get("explanation"):
            opts["_explanation"] = q["explanation"][:600]
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
    form_code = next_gen_form_code(conn)
    print(f"=== generating {form_code} with Sonnet ===\n", flush=True)
    total_cost = 0.0
    summary = []
    for section in ("english", "math", "reading", "science"):
        data, cost = generate_section(section)
        total_cost += cost
        if not data:
            print(f"  {section} FAILED", flush=True)
            continue
        result = insert_section(conn, form_code, section, data)
        if result:
            tid, n = result
            print(f"  ✓ {section}: test_id={tid}, {n} questions inserted\n", flush=True)
            summary.append((section, n))
    print(f"=== DONE — {form_code} ===", flush=True)
    print(f"  total cost: ~${total_cost:.3f}", flush=True)
    for sec, n in summary:
        print(f"  {sec}: {n} questions", flush=True)


if __name__ == "__main__":
    main()
