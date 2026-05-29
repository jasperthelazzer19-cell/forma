"""Diagnostic flow: 5-question math warm-up that seeds the user's dashboard
with a projected ACT score so the empty state has a hook.

Routes:
  GET  /diagnostic         — one-at-a-time 5-Q flow (all sent, JS-driven)
  POST /diagnostic/submit  — grade + save to user_settings
  GET  /diagnostic/result  — projected score + CTAs

No auth — single-user app. State stored in user_settings table.
"""
import json
import sqlite3
from datetime import datetime
from flask import render_template_string, request, jsonify, redirect

from forma.db import db


# ─── Score mapping ──────────────────────────────────────────────────────────
# Rough ACT math-scale curve. 5 questions is tiny so the result is directional,
# not diagnostic-grade — we frame it that way in the UI.
def _project_math(pct):
    """pct 0-100 → ACT math scale 1-36.
    Must match features.predict_score.pct_to_scaled so the diagnostic and the
    dashboard never show a different projection for the same percentage."""
    if pct >= 90: return 33
    if pct >= 80: return 30
    if pct >= 70: return 27
    if pct >= 60: return 24
    if pct >= 50: return 21
    if pct >= 40: return 18
    if pct >= 30: return 15
    if pct >= 20: return 12
    return 9


# ─── Question selection ─────────────────────────────────────────────────────
def _pick_questions(n=5):
    """Pick n official math questions, all from different tests for variety."""
    conn = db()
    cur = conn.cursor()
    # Get candidate pool: official math questions with intact options + correct answer
    rows = cur.execute("""
        SELECT q.test_id, q.q_num, q.options_json, q.correct_answer, q.topic
        FROM questions q
        JOIN tests t ON t.id = q.test_id
        WHERE t.section='math' AND t.source='official'
          AND q.options_json IS NOT NULL
          AND q.correct_answer IS NOT NULL
          AND length(q.correct_answer) >= 1
        ORDER BY RANDOM()
        LIMIT 200
    """).fetchall()

    items = []
    seen_tests = set()
    for r in rows:
        if r["test_id"] in seen_tests:
            continue
        try:
            opts = json.loads(r["options_json"])
        except Exception:
            continue
        prompt = opts.pop("_prompt", "").strip()
        opts.pop("_explanation", None)
        # Need at least 4 options and a prompt
        if not prompt or len(opts) < 4:
            continue
        items.append({
            "test_id": r["test_id"],
            "q_num": r["q_num"],
            "prompt": prompt,
            "options": opts,  # dict: { "A": "text", "B": "text", ... }
            "correct": r["correct_answer"].strip().upper(),
            "topic": r["topic"] or "",
        })
        seen_tests.add(r["test_id"])
        if len(items) >= n:
            break
    return items


# ─── HTML ───────────────────────────────────────────────────────────────────
DIAGNOSTIC_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnostic — Forma</title>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0805; --bg-2:#0e0a05; --panel:#15110a; --panel-2:#1e1810;
  --line:#241c11; --line-2:#36291a;
  --fg:#f3e7d3; --fg-2:#d4c5a8; --muted:#8a7a5e; --dim:#5a4a36;
  --amber:#e8a64a; --amber-2:#ffb24e; --amber-soft:rgba(232,166,74,0.12);
  --green:#7dd87f; --red:#e87a6a; --paper:#f8f1dd;
  --sans:"Switzer",-apple-system,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.55;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
body{
  background:
    radial-gradient(60% 50% at 50% -5%,rgba(232,166,74,0.08),transparent 70%),
    linear-gradient(180deg,#0a0805 0%, #060402 100%);
  min-height:100vh;display:flex;flex-direction:column;
}
a{color:inherit;text-decoration:none}

.topbar{
  display:flex;align-items:center;justify-content:space-between;
  padding:18px 32px;border-bottom:1px solid var(--line);
}
.brand{font-weight:600;font-size:18px;letter-spacing:-0.025em}
.brand .dot{color:var(--amber);font-size:0.55em;vertical-align:0.4em;margin-left:2px}
.skip{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.1em;text-transform:uppercase}
.skip:hover{color:var(--fg-2)}

.progress{
  display:flex;justify-content:center;gap:10px;padding:24px 0 0;
}
.progress .dot{width:32px;height:3px;border-radius:2px;background:var(--line-2);transition:background .25s}
.progress .dot.done{background:var(--amber)}
.progress .dot.active{background:var(--amber-2);box-shadow:0 0 12px rgba(232,166,74,0.5)}

.stage{
  flex:1;display:flex;align-items:center;justify-content:center;
  padding:40px 24px;max-width:760px;margin:0 auto;width:100%;
}
.card{width:100%}
.qmeta{
  font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.14em;
  text-transform:uppercase;margin-bottom:14px;display:flex;justify-content:space-between;
}
.qmeta .topic{color:var(--amber)}
.qprompt{
  font-size:22px;line-height:1.45;font-weight:500;letter-spacing:-0.012em;margin-bottom:26px;
  color:var(--fg);
}
.opts{display:flex;flex-direction:column;gap:10px}
.opt{
  display:flex;align-items:flex-start;gap:14px;padding:14px 18px;
  border:1px solid var(--line-2);border-radius:8px;background:var(--panel);
  cursor:pointer;transition:border-color .15s,background .15s,transform .08s;
  font-size:15px;line-height:1.5;color:var(--fg);
}
.opt:hover{border-color:var(--amber);background:var(--panel-2)}
.opt:active{transform:scale(0.997)}
.opt .k{
  font-family:var(--mono);font-weight:600;color:var(--amber);min-width:18px;
  flex-shrink:0;letter-spacing:0.04em;font-size:13px;line-height:1.7;
}
.opt .t{flex:1}
.opt.picked{border-color:var(--amber);background:var(--amber-soft)}
.opt.correct{border-color:var(--green);background:rgba(125,216,127,0.08)}
.opt.wrong{border-color:var(--red);background:rgba(232,122,106,0.06)}
.opt.dim{opacity:0.45}
.opt.locked{cursor:default}
.opt.locked:hover{border-color:var(--line-2);background:var(--panel)}
.opt.correct:hover,.opt.wrong:hover{background:inherit;border-color:inherit}

.feedback{
  margin-top:18px;padding:14px 18px;border-radius:8px;font-size:14px;line-height:1.55;
  display:none;
}
.feedback.show{display:block}
.feedback.good{background:rgba(125,216,127,0.08);border:1px solid rgba(125,216,127,0.25);color:#a8e2aa}
.feedback.bad{background:rgba(232,122,106,0.06);border:1px solid rgba(232,122,106,0.25);color:#f0a99c}

.next-row{
  margin-top:24px;display:flex;justify-content:flex-end;
}
.next{
  font-family:var(--mono);font-size:12px;letter-spacing:0.08em;text-transform:uppercase;
  padding:11px 22px;background:var(--paper);color:var(--bg);border:none;cursor:pointer;
  display:none;transition:transform .1s;font-weight:500;
}
.next.show{display:inline-flex;align-items:center;gap:8px}
.next:hover{transform:translateX(2px)}

.loading{
  position:fixed;inset:0;display:none;align-items:center;justify-content:center;
  background:rgba(10,8,5,0.85);backdrop-filter:blur(8px);z-index:50;
}
.loading.show{display:flex}
.loading .pulse{font-family:var(--mono);font-size:13px;color:var(--amber);letter-spacing:0.2em;text-transform:uppercase;animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:0.4}50%{opacity:1}}
</style></head><body>

<div class="topbar">
  <a href="/" class="brand">Forma<span class="dot">●</span></a>
  <a href="/app" class="skip">Skip →</a>
</div>

<div class="progress" id="progress">
  {% for q in questions %}<span class="dot {% if loop.first %}active{% endif %}"></span>{% endfor %}
</div>

<div class="stage">
  <div class="card" id="card"></div>
</div>

<div class="loading" id="loading"><div class="pulse">Scoring…</div></div>

<script>
const QUESTIONS = {{ questions_json|safe }};
let idx = 0;
let answers = [];

function render(){
  const q = QUESTIONS[idx];
  const card = document.getElementById('card');
  const opts = Object.entries(q.options).map(([k,v]) => `
    <div class="opt" data-key="${k}">
      <span class="k">${k}</span><span class="t">${v}</span>
    </div>`).join('');
  card.innerHTML = `
    <div class="qmeta">
      <span>QUESTION ${idx+1} / ${QUESTIONS.length} · MATH</span>
      <span class="topic">${q.topic ? q.topic.toUpperCase() : 'OFFICIAL ACT'}</span>
    </div>
    <div class="qprompt">${q.prompt}</div>
    <div class="opts" id="opts">${opts}</div>
    <div class="feedback" id="feedback"></div>
    <div class="next-row"><button class="next" id="next">${idx === QUESTIONS.length-1 ? 'See result' : 'Next'} →</button></div>
  `;
  // Update progress dots
  document.querySelectorAll('#progress .dot').forEach((d,i) => {
    d.classList.remove('active','done');
    if (i < idx) d.classList.add('done');
    if (i === idx) d.classList.add('active');
  });
  // Bind options
  document.querySelectorAll('#opts .opt').forEach(el => {
    el.addEventListener('click', () => pick(el.dataset.key));
  });
  document.getElementById('next').addEventListener('click', advance);
}

function pick(key){
  const q = QUESTIONS[idx];
  const correct = q.correct;
  const isCorrect = key === correct;
  answers.push({test_id: q.test_id, q_num: q.q_num, user: key, correct: correct});
  // Lock options, show right/wrong
  document.querySelectorAll('#opts .opt').forEach(el => {
    el.classList.add('locked');
    const k = el.dataset.key;
    if (k === correct) el.classList.add('correct');
    else if (k === key) el.classList.add('wrong');
    else el.classList.add('dim');
  });
  const fb = document.getElementById('feedback');
  if (isCorrect) {
    fb.className = 'feedback show good';
    fb.textContent = 'Correct.';
  } else {
    fb.className = 'feedback show bad';
    fb.textContent = `Answer: ${correct}. We'll explain why in the app — for now, the diagnostic just notes the miss.`;
  }
  document.getElementById('next').classList.add('show');
}

function advance(){
  if (idx < QUESTIONS.length - 1) {
    idx += 1;
    render();
    window.scrollTo({top: 0, behavior: 'smooth'});
  } else {
    submit();
  }
}

async function submit(){
  document.getElementById('loading').classList.add('show');
  try {
    const res = await fetch('/diagnostic/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({answers})
    });
    const data = await res.json();
    window.location.href = data.redirect || '/diagnostic/result';
  } catch (e) {
    alert('Network error — refresh and try again.');
    document.getElementById('loading').classList.remove('show');
  }
}

render();
</script>
</body></html>
"""


DIAGNOSTIC_RESULT_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnostic Result — Forma</title>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0805; --panel:#15110a; --panel-2:#1e1810;
  --line:#241c11; --line-2:#36291a;
  --fg:#f3e7d3; --fg-2:#d4c5a8; --muted:#8a7a5e;
  --amber:#e8a64a; --amber-2:#ffb24e; --amber-soft:rgba(232,166,74,0.12);
  --paper:#f8f1dd;
  --sans:"Switzer",-apple-system,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
body{
  background:
    radial-gradient(60% 50% at 50% -5%,rgba(232,166,74,0.10),transparent 70%),
    linear-gradient(180deg,#0a0805 0%, #060402 100%);
  min-height:100vh;
}
a{color:inherit;text-decoration:none}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:18px 32px;border-bottom:1px solid var(--line)}
.brand{font-weight:600;font-size:18px;letter-spacing:-0.025em}
.brand .dot{color:var(--amber);font-size:0.55em;vertical-align:0.4em;margin-left:2px}

.wrap{max-width:760px;margin:0 auto;padding:60px 24px 40px}
.eyebrow{font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:0.18em;text-transform:uppercase;margin-bottom:14px}
h1{font-size:42px;line-height:1.05;font-weight:600;letter-spacing:-0.028em;margin-bottom:14px}
h1 em{font-style:italic;color:var(--amber);font-weight:500}
.lead{color:var(--fg-2);font-size:17px;max-width:55ch;margin-bottom:36px;line-height:1.55}

.score-card{
  border:1px solid var(--line-2);border-radius:12px;padding:36px;background:var(--panel);
  display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px;position:relative;overflow:hidden;
}
.score-card::before{content:"";position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--amber),transparent);opacity:0.4}
.score-block .label{font-family:var(--mono);font-size:10.5px;color:var(--muted);letter-spacing:0.16em;text-transform:uppercase;margin-bottom:10px}
.score-block .v{font-size:64px;font-weight:600;letter-spacing:-0.04em;line-height:1;color:var(--fg)}
.score-block .v.amber{color:var(--amber)}
.score-block .sub{font-size:13px;color:var(--muted);margin-top:8px;font-family:var(--mono);letter-spacing:0.04em}
@media(max-width:600px){.score-card{grid-template-columns:1fr;gap:30px}.score-block .v{font-size:54px}}

.caveat{
  background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
  padding:14px 18px;font-size:13.5px;color:var(--fg-2);line-height:1.55;margin-bottom:36px;
}
.caveat b{color:var(--fg)}

.cta-row{display:flex;gap:12px;flex-wrap:wrap}
.btn-p{
  padding:12px 24px;background:var(--paper);color:var(--bg);font-family:var(--mono);font-size:12px;
  font-weight:500;letter-spacing:0.08em;text-transform:uppercase;cursor:pointer;display:inline-flex;
  align-items:center;gap:8px;transition:transform .1s;
}
.btn-p:hover{transform:translateX(2px)}
.btn-s{
  padding:12px 24px;background:transparent;color:var(--fg-2);font-family:var(--mono);font-size:12px;
  letter-spacing:0.08em;text-transform:uppercase;border:1px solid var(--line-2);
  display:inline-flex;align-items:center;gap:8px;transition:border-color .15s,color .15s;
}
.btn-s:hover{border-color:var(--amber);color:var(--amber)}
</style></head><body>

<div class="topbar">
  <a href="/" class="brand">Forma<span class="dot">●</span></a>
</div>

<div class="wrap">
  <div class="eyebrow">5-QUESTION MATH WARM-UP · COMPLETE</div>
  <h1>Your baseline:<br><em>{{ projected_math }} ACT math</em></h1>
  <p class="lead">Based on {{ correct }} of {{ total }} correct on 5 random official ACT math questions. Directional — your real score will move as you drill more.</p>

  <div class="score-card">
    <div class="score-block">
      <div class="label">Projected Math</div>
      <div class="v amber">{{ projected_math }}</div>
      <div class="sub">/ 36 · {{ pct_math }}% correct</div>
    </div>
    <div class="score-block">
      <div class="label">Composite Estimate</div>
      <div class="v">{{ projected_math }}<span style="color:var(--muted);font-size:0.4em;font-weight:500"> ±3</span></div>
      <div class="sub">until other sections drilled</div>
    </div>
  </div>

  <div class="caveat">
    <b>Why ±3?</b> Composite is the average of all four sections. We've only measured math — your real composite depends on English, Reading, and Science too. Drill those to tighten the estimate.
  </div>

  <div class="cta-row">
    <a href="/app" class="btn-p">Open dashboard →</a>
    <a href="/adaptive" class="btn-s">Start adaptive session</a>
    <a href="/section/math" class="btn-s">Browse math tests</a>
  </div>
</div>
</body></html>
"""


# ─── Route handlers ─────────────────────────────────────────────────────────
def diagnostic_view():
    items = _pick_questions(5)
    if len(items) < 5:
        # Not enough official math questions — shouldn't happen with current data
        return redirect("/app")
    # Don't ship `correct` in the data we send to the client unmasked — but for
    # this lightweight flow we do, since the user can't game what they're not
    # graded against externally. Acceptable for a diagnostic. If we ever care,
    # send correct on submit roundtrip instead.
    questions_json = json.dumps([{
        "test_id": q["test_id"], "q_num": q["q_num"],
        "prompt": q["prompt"], "options": q["options"],
        "correct": q["correct"], "topic": q["topic"],
    } for q in items])
    return render_template_string(DIAGNOSTIC_HTML,
                                  questions=items,
                                  questions_json=questions_json)


def diagnostic_submit():
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", [])
    if not answers:
        return jsonify({"error": "no answers"}), 400

    correct_count = sum(1 for a in answers if a.get("user") == a.get("correct"))
    total = len(answers)
    pct = (correct_count * 100.0 / total) if total else 0.0
    projected_math = _project_math(pct)

    payload = {
        "correct": correct_count,
        "total": total,
        "pct_math": round(pct),
        "projected_math": projected_math,
        "projected_composite": projected_math,  # math-only estimate
        "taken_at": datetime.utcnow().isoformat(timespec="seconds"),
    }

    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
                ("diagnostic_taken", "1"))
    cur.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
                ("diagnostic_result", json.dumps(payload)))
    conn.commit()

    return jsonify({"redirect": "/diagnostic/result", **payload})


def diagnostic_result():
    conn = db()
    cur = conn.cursor()
    row = cur.execute("SELECT value FROM user_settings WHERE key='diagnostic_result'").fetchone()
    if not row:
        return redirect("/diagnostic")
    result = json.loads(row["value"])
    return render_template_string(DIAGNOSTIC_RESULT_HTML, **result)


# ─── Helpers exposed for /app banner check ──────────────────────────────────
def diagnostic_status():
    """Returns dict: {taken: bool, result: dict|None}."""
    conn = db()
    cur = conn.cursor()
    taken = cur.execute("SELECT value FROM user_settings WHERE key='diagnostic_taken'").fetchone()
    if not taken or taken["value"] != "1":
        return {"taken": False, "result": None}
    res = cur.execute("SELECT value FROM user_settings WHERE key='diagnostic_result'").fetchone()
    result = json.loads(res["value"]) if res else None
    return {"taken": True, "result": result}


def register(app):
    app.add_url_rule("/diagnostic", "diagnostic_view", diagnostic_view)
    app.add_url_rule("/diagnostic/submit", "diagnostic_submit", diagnostic_submit, methods=["POST"])
    app.add_url_rule("/diagnostic/result", "diagnostic_result", diagnostic_result)
