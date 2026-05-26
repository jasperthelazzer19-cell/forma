"""
Pre-generate AI explanations for every official-source question that doesn't
already have one. Stores them in options_json["_explanation"].

Idempotent: skips questions whose options_json already has _explanation.
Parallel: 6 concurrent gpt-4o-mini calls.
"""
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
MODEL = "gpt-4o-mini"
SOURCES = ("official",)  # change via CLI args
WORKERS = 6
PRICE_IN = 0.15 / 1e6
PRICE_OUT = 0.60 / 1e6

# Load OpenAI key from vault
with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    for cand in re.findall(r"sk-(?:proj-|[a-zA-Z])[a-zA-Z0-9_-]{20,}", f.read()):
        if not cand.startswith("sk-ant"):
            os.environ["OPENAI_API_KEY"] = cand
            break
oai = OpenAI()

SYSTEM = """You're an ACT tutor explaining one multiple-choice question to a
high school junior. Be concise, specific, direct. In 3-5 sentences:
1. State why the correct answer is right (the actual rule or reading skill).
2. Briefly explain why the most plausible wrong answer is wrong.
No fluff. No 'great question!' No restating the question. Plain prose.
Use the passage context when relevant. Don't use HTML or markdown."""


def fetch_pending(conn, sources, limit=None):
    """Return list of (test_id, q_num, passage_text, options_json, correct) needing explanation."""
    src_in = ",".join(f"'{s}'" for s in sources)
    sql = f"""SELECT t.id, t.passage_text, q.q_num, q.options_json, q.correct_answer
              FROM questions q
              JOIN tests t ON t.id = q.test_id
              WHERE t.source IN ({src_in})
              ORDER BY t.id, q.q_num"""
    rows = []
    for r in conn.execute(sql).fetchall():
        try:
            opts = json.loads(r[3] or "{}")
        except Exception:
            continue
        if opts.get("_explanation"):
            continue
        if not r[4]:  # no correct answer stored, can't write a confident explanation
            continue
        rows.append({"test_id": r[0], "passage": r[1] or "",
                     "q_num": r[2], "opts": opts, "correct": r[4]})
        if limit and len(rows) >= limit:
            break
    return rows


def explain_one(item):
    """Call OpenAI for one question. Returns (item, explanation, cost) or (item, None, 0)."""
    opts = item["opts"]
    prompt = opts.get("_prompt", "")
    choices = [(k, v) for k, v in sorted(opts.items()) if len(k) == 1]
    if not choices:
        return item, None, 0.0
    opt_str = "\n".join(f"{k}. {v}" for k, v in choices)
    passage = item["passage"][:1500] if item["passage"] else ""
    user_parts = []
    if passage:
        user_parts.append(f"PASSAGE EXCERPT:\n{passage}\n")
    if prompt:
        user_parts.append(f"QUESTION:\n{prompt}\n")
    user_parts.append(f"OPTIONS:\n{opt_str}\n")
    user_parts.append(f"CORRECT: {item['correct']}")
    user = "\n".join(user_parts)
    try:
        r = oai.chat.completions.create(
            model=MODEL, max_tokens=350,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        text = r.choices[0].message.content.strip()
        cost = r.usage.prompt_tokens * PRICE_IN + r.usage.completion_tokens * PRICE_OUT
        return item, text, cost
    except Exception as e:
        print(f"  err q{item['q_num']} (test {item['test_id']}): {type(e).__name__}: {str(e)[:140]}", flush=True)
        return item, None, 0.0


def main():
    sources = SOURCES
    if len(sys.argv) > 1:
        sources = tuple(sys.argv[1:])
    conn = sqlite3.connect(DB, timeout=30)
    print(f"=== fetching questions needing explanation (sources={sources}) ===", flush=True)
    pending = fetch_pending(conn, sources)
    print(f"=== {len(pending)} questions pending ===", flush=True)
    if not pending:
        print("nothing to do")
        return
    # Estimate cost: ~400 tokens input + 200 output average
    est = len(pending) * (400 * PRICE_IN + 200 * PRICE_OUT)
    print(f"=== estimated max cost: ${est:.2f} ===", flush=True)
    grand_cost = 0.0
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(explain_one, it) for it in pending]
        for fut in as_completed(futures):
            item, expl, cost = fut.result()
            done += 1
            grand_cost += cost
            if not expl:
                continue
            # Read current options_json (may have been updated by other workers in same test_id)
            row = conn.execute("SELECT options_json FROM questions WHERE test_id=? AND q_num=?",
                               (item["test_id"], item["q_num"])).fetchone()
            opts = json.loads(row[0] or "{}")
            opts["_explanation"] = expl
            conn.execute("UPDATE questions SET options_json=? WHERE test_id=? AND q_num=?",
                         (json.dumps(opts, ensure_ascii=False), item["test_id"], item["q_num"]))
            if done % 25 == 0 or done == len(pending):
                conn.commit()
                elapsed = int(time.time() - t0)
                rate = done / max(1, elapsed)
                eta = int((len(pending) - done) / rate) if rate else 0
                print(f"  [{done:>5}/{len(pending)}] ${grand_cost:.2f}, "
                      f"{elapsed}s, ETA {eta//60}m{eta%60}s", flush=True)
    conn.commit()
    print(f"\n=== DONE: {done} explained, ${grand_cost:.3f} spent ===", flush=True)


if __name__ == "__main__":
    main()
