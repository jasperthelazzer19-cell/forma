"""Tag every math question with its ACT topic + difficulty.

Uses GPT-4o-mini (cheap, ~$0.10/M output tokens, ~$0.15/M input).
For ~6800 math questions in batches of 50: ~$1-2 total.

Tags written to questions.topic and questions.difficulty.
"""
import json
import os
import re
import sqlite3
import time

from openai import OpenAI

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"

with open("/Users/jasperlasser/Downloads/company brain/Jlazz/Projects/CreatorBrain/Credentials.md") as f:
    txt = f.read()
for cand in re.findall(r"sk-(?:proj-|[a-zA-Z])[a-zA-Z0-9_-]{20,}", txt):
    if not cand.startswith("sk-ant"):
        os.environ["OPENAI_API_KEY"] = cand
        break
client = OpenAI()

TOPICS = ["Pre-Algebra", "Elementary Algebra", "Intermediate Algebra",
          "Plane Geometry", "Coordinate Geometry", "Trigonometry",
          "Statistics", "Functions"]

SYSTEM = f"""You tag ACT Math questions by topic and difficulty.
Topics: {', '.join(TOPICS)}.
Difficulty: easy, medium, hard.

Output JSON: {{"tags": [{{"q_num": 1, "topic": "Pre-Algebra", "difficulty": "easy"}}, ...]}}
"""


def fetch_batch(conn, limit=50):
    """Fetch math questions without a topic, batched."""
    return conn.execute("""
        SELECT q.test_id, q.q_num, q.options_json
        FROM questions q JOIN tests t ON t.id = q.test_id
        WHERE t.section = 'math' AND (q.topic IS NULL OR q.topic = '')
        LIMIT ?
    """, (limit,)).fetchall()


def tag_batch(rows):
    items = []
    for r in rows:
        opts = json.loads(r["options_json"] or "{}")
        prompt = opts.pop("_prompt", "") or ""
        opts.pop("_explanation", None)
        opt_str = "  ".join(f"{k}.{v[:60]}" for k, v in opts.items() if len(k) == 1)
        items.append(f"Q{r['q_num']}: {prompt[:200]} {opt_str}".strip())
    user = "\n".join(items)
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini", max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(r.choices[0].message.content)
    except Exception as e:
        print(f"  API error: {e}", flush=True)
        return None


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    total_done = 0
    while True:
        rows = fetch_batch(conn, 50)
        if not rows:
            break
        result = tag_batch(rows)
        if not result or "tags" not in result:
            print("  batch failed, skipping 50", flush=True)
            # Mark them as 'untagged' so we don't infinite-loop
            for r in rows:
                conn.execute("UPDATE questions SET topic = 'Unknown' WHERE test_id=? AND q_num=?",
                             (r["test_id"], r["q_num"]))
            conn.commit()
            continue
        # Map q_num → row
        by_qnum = {r["q_num"]: r for r in rows}
        for tag in result["tags"]:
            qnum = tag.get("q_num")
            topic = tag.get("topic")
            diff = tag.get("difficulty")
            if qnum in by_qnum and topic:
                r = by_qnum[qnum]
                conn.execute(
                    "UPDATE questions SET topic=?, difficulty=? WHERE test_id=? AND q_num=?",
                    (topic, diff, r["test_id"], r["q_num"])
                )
        conn.commit()
        total_done += len(rows)
        print(f"  tagged batch: total={total_done}", flush=True)
        time.sleep(0.3)
    print(f"DONE — tagged {total_done} math questions", flush=True)


if __name__ == "__main__":
    main()
