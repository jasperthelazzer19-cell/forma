"""Drill loop: one-question-at-a-time with instant feedback + tutor.

Routes:
  GET  /drill                — pick N questions and run the loop (one tab)
  POST /drill/submit         — grade + persist attempt + return result payload

Query params for GET /drill:
  ?section=math|english|reading|science   (default: math)
  ?topic=<slug>                           (overrides section)
  ?n=10                                   (default: 10, max 25)
  ?source=official|generated|crackab|any  (default: official, falls back if empty)

Saves attempts via the same `attempts` + `attempt_answers` tables the rest of
the app uses, so the dashboard/streak/etc. all "just work."
"""
import json
import sqlite3
from datetime import datetime
from flask import render_template_string, request, jsonify, redirect

from forma.db import db


# ─── Question selection ─────────────────────────────────────────────────────
SECTIONS = {"english", "math", "reading", "science"}


def _pick_questions(section=None, topic=None, n=10, source="official"):
    """Returns list of question dicts. Skips passage-heavy questions when
    we can (passage context isn't shown in drill mode yet)."""
    conn = db()
    cur = conn.cursor()
    where = ["q.options_json IS NOT NULL",
             "q.correct_answer IS NOT NULL",
             "length(q.correct_answer) >= 1"]
    params = []
    if topic:
        where.append("q.topic = ?")
        params.append(topic)
    elif section and section in SECTIONS:
        where.append("t.section = ?")
        params.append(section)
    if source and source != "any":
        where.append("t.source = ?")
        params.append(source)
    # For now, drill avoids reading/english tests with passages — they need
    # passage context shown which the drill view doesn't yet support.
    # Math + Science work standalone.
    if not topic and section in {"english", "reading"}:
        # Allow but de-prioritize — caller can request explicitly via topic
        pass

    sql = f"""
        SELECT q.test_id, q.q_num, q.options_json, q.correct_answer, q.topic,
               t.section, t.title, t.passage_text
        FROM questions q
        JOIN tests t ON t.id = q.test_id
        WHERE {' AND '.join(where)}
        ORDER BY RANDOM()
        LIMIT {min(int(n) * 4, 200)}
    """
    rows = cur.execute(sql, params).fetchall()

    items = []
    for r in rows:
        try:
            opts = json.loads(r["options_json"])
        except Exception:
            continue
        prompt = opts.pop("_prompt", "").strip()
        explanation = opts.pop("_explanation", "").strip()
        opt_keys = sorted([k for k in opts.keys() if len(k) == 1])
        if not prompt or len(opt_keys) < 4:
            continue
        items.append({
            "test_id": r["test_id"],
            "q_num": r["q_num"],
            "section": r["section"],
            "test_title": (r["title"] or "")[:40],
            "topic": r["topic"] or "",
            "prompt": prompt,
            "options": {k: opts[k] for k in opt_keys},
            "correct": r["correct_answer"].strip().upper(),
            "explanation": explanation,
            # Pass a short passage snippet for reading/english when available
            "passage_snippet": (r["passage_text"] or "")[:600] if r["section"] in {"english","reading"} else "",
        })
        if len(items) >= n:
            break
    return items


# ─── Persist attempt (one drill = one "attempt" row) ────────────────────────
def _save_attempt(items, answers, duration_seconds):
    """Save the drill as a single attempt grouped by test_id (or synthetic).
    For simplicity, we save one attempt per test_id touched in this drill,
    because attempt_answers is PK'd on (attempt_id, q_num) and q_nums may
    repeat across tests."""
    if not items:
        return None
    conn = db()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")

    # Group answers by test_id
    by_test = {}
    for item in items:
        a = answers.get(f"{item['test_id']}:{item['q_num']}")
        if not a:
            continue
        is_correct = 1 if a.upper() == item["correct"] else 0
        by_test.setdefault(item["test_id"], []).append({
            "q_num": item["q_num"], "user": a, "correct": item["correct"], "is_correct": is_correct,
        })

    last_aid = None
    for test_id, rows in by_test.items():
        score = sum(r["is_correct"] for r in rows)
        total = len(rows)
        pct = (score * 100.0 / total) if total else 0.0
        cur.execute("""INSERT INTO attempts (test_id, started_at, finished_at,
                       duration_seconds, score, total, pct) VALUES (?,?,?,?,?,?,?)""",
                    (test_id, now, now,
                     int(duration_seconds / max(1, len(by_test))), score, total, pct))
        aid = cur.lastrowid
        last_aid = aid
        for r in rows:
            try:
                cur.execute("""INSERT INTO attempt_answers
                               (attempt_id, q_num, user_answer, correct_answer, is_correct)
                               VALUES (?,?,?,?,?)""",
                            (aid, r["q_num"], r["user"], r["correct"], r["is_correct"]))
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    return last_aid


# ─── HTML ───────────────────────────────────────────────────────────────────
DRILL_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drill — Forma</title>
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
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
body{
  background:
    radial-gradient(60% 50% at 50% -5%,rgba(232,166,74,0.08),transparent 70%),
    linear-gradient(180deg,#0a0805 0%, #060402 100%);
  min-height:100vh;display:flex;flex-direction:column;
}
a{color:inherit;text-decoration:none}

.topbar{display:flex;align-items:center;justify-content:space-between;padding:18px 32px;border-bottom:1px solid var(--line)}
.brand{font-weight:600;font-size:18px;letter-spacing:-0.025em}
.brand .dot{color:var(--amber);font-size:0.55em;vertical-align:0.4em;margin-left:2px}
.top-right{display:flex;align-items:center;gap:18px}
.runtag{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.14em;text-transform:uppercase}
.runtag .a{color:var(--amber)}
.exit{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.1em;text-transform:uppercase}
.exit:hover{color:var(--fg-2)}

.progress{display:flex;justify-content:center;gap:6px;padding:22px 0 0;flex-wrap:wrap;max-width:600px;margin:0 auto}
.progress .dot{width:22px;height:3px;border-radius:2px;background:var(--line-2);transition:background .25s}
.progress .dot.done{background:var(--amber)}
.progress .dot.wrong{background:var(--red);opacity:0.6}
.progress .dot.active{background:var(--amber-2);box-shadow:0 0 12px rgba(232,166,74,0.5)}

.stage{flex:1;display:flex;align-items:flex-start;justify-content:center;padding:40px 24px;max-width:820px;margin:0 auto;width:100%}
.card{width:100%}
.qmeta{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.14em;text-transform:uppercase;margin-bottom:14px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.qmeta .topic{color:var(--amber)}
.passage{font-family:var(--sans);font-size:14.5px;color:var(--fg-2);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px 22px;margin-bottom:18px;max-height:220px;overflow:auto;line-height:1.6}
.qprompt{font-size:22px;line-height:1.45;font-weight:500;letter-spacing:-0.012em;margin-bottom:24px;color:var(--fg)}
.opts{display:flex;flex-direction:column;gap:10px}
.opt{
  display:flex;align-items:flex-start;gap:14px;padding:14px 18px;
  border:1px solid var(--line-2);border-radius:8px;background:var(--panel);
  cursor:pointer;transition:border-color .15s,background .15s,transform .08s;
  font-size:15px;line-height:1.5;color:var(--fg);text-align:left;
}
.opt:hover{border-color:var(--amber);background:var(--panel-2)}
.opt:active{transform:scale(0.997)}
.opt .k{font-family:var(--mono);font-weight:600;color:var(--amber);min-width:18px;flex-shrink:0;letter-spacing:0.04em;font-size:13px;line-height:1.7}
.opt .t{flex:1}
.opt.correct{border-color:var(--green);background:rgba(125,216,127,0.08)}
.opt.wrong{border-color:var(--red);background:rgba(232,122,106,0.06)}
.opt.dim{opacity:0.4}
.opt.locked{cursor:default}
.opt.locked:hover{background:var(--panel)}
.opt.correct.locked:hover{background:rgba(125,216,127,0.08);border-color:var(--green)}
.opt.wrong.locked:hover{background:rgba(232,122,106,0.06);border-color:var(--red)}

.feedback{margin-top:18px;display:none}
.feedback.show{display:block}
.feedback .row{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:11.5px;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px}
.feedback.good .row{color:var(--green)}
.feedback.bad .row{color:var(--red)}
.feedback .explain{
  background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:14px 18px;
  font-size:14px;line-height:1.6;color:var(--fg-2);
}
.feedback .explain b{color:var(--fg)}
.feedback .explain.placeholder{color:var(--muted);font-style:italic}
.feedback .tutor-cta{
  margin-top:10px;font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:0.08em;
  text-transform:uppercase;cursor:pointer;background:transparent;border:none;padding:0;
}
.feedback .tutor-cta:hover{text-decoration:underline}

.next-row{margin-top:24px;display:flex;justify-content:space-between;align-items:center;gap:12px}
.next-row .bookmark{
  font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.1em;text-transform:uppercase;
  background:transparent;border:1px solid var(--line-2);padding:8px 14px;cursor:pointer;
}
.next-row .bookmark:hover{color:var(--amber);border-color:var(--amber)}
.next-row .bookmark.on{color:var(--amber);border-color:var(--amber)}
.next{
  font-family:var(--mono);font-size:12px;letter-spacing:0.08em;text-transform:uppercase;
  padding:11px 22px;background:var(--paper);color:var(--bg);border:none;cursor:pointer;
  display:none;transition:transform .1s;font-weight:500;
}
.next.show{display:inline-flex;align-items:center;gap:8px}
.next:hover{transform:translateX(2px)}

.loading{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:rgba(10,8,5,0.85);backdrop-filter:blur(8px);z-index:50}
.loading.show{display:flex}
.loading .pulse{font-family:var(--mono);font-size:13px;color:var(--amber);letter-spacing:0.2em;text-transform:uppercase;animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:0.4}50%{opacity:1}}
</style></head><body>

<div class="topbar">
  <a href="/" class="brand">Forma<span class="dot">●</span></a>
  <div class="top-right">
    <span class="runtag">{{ run_label|safe }} · <span class="a" id="counter">0/{{ questions|length }} correct</span></span>
    <a href="/app" class="exit">Exit →</a>
  </div>
</div>

<div class="progress" id="progress">
  {% for q in questions %}<span class="dot {% if loop.first %}active{% endif %}"></span>{% endfor %}
</div>

<div class="stage">
  <div class="card" id="card"></div>
</div>

<div class="loading" id="loading"><div class="pulse">Saving…</div></div>

<script>
const QUESTIONS = {{ questions_json|safe }};
const RUN_PARAMS = {{ run_params_json|safe }};
let idx = 0;
let correctCount = 0;
let startedAt = Date.now();
let answers = {};  // "test_id:q_num" -> user letter
let tutorCache = {}; // "test_id:q_num" -> html

function progressDot(i, cls){
  const d = document.querySelectorAll('#progress .dot')[i];
  if (!d) return;
  d.classList.remove('active');
  d.classList.add(cls);
}

function render(){
  const q = QUESTIONS[idx];
  const card = document.getElementById('card');
  const opts = Object.entries(q.options).map(([k,v]) => `
    <div class="opt" data-key="${k}">
      <span class="k">${k}</span><span class="t">${v}</span>
    </div>`).join('');
  const passage = q.passage_snippet
    ? `<div class="passage">${q.passage_snippet}${q.passage_snippet.length >= 600 ? '…' : ''}</div>`
    : '';
  card.innerHTML = `
    <div class="qmeta">
      <span>QUESTION ${idx+1} / ${QUESTIONS.length} · ${q.section.toUpperCase()}</span>
      <span class="topic">${q.topic ? q.topic.toUpperCase() : (q.test_title || '').toUpperCase()}</span>
    </div>
    ${passage}
    <div class="qprompt">${q.prompt}</div>
    <div class="opts" id="opts">${opts}</div>
    <div class="feedback" id="feedback"></div>
    <div class="next-row">
      <button class="bookmark" id="bm" title="Mark for review">☆ Bookmark</button>
      <button class="next" id="next">${idx === QUESTIONS.length-1 ? 'Finish drill' : 'Next'} →</button>
    </div>
  `;
  // Update progress active dot
  document.querySelectorAll('#progress .dot').forEach((d,i) => {
    if (!d.classList.contains('done') && !d.classList.contains('wrong')) {
      d.classList.toggle('active', i === idx);
    }
  });
  document.querySelectorAll('#opts .opt').forEach(el => {
    el.addEventListener('click', () => pick(el.dataset.key));
  });
  document.getElementById('next').addEventListener('click', advance);
  document.getElementById('bm').addEventListener('click', toggleBookmark);
}

function pick(key){
  const q = QUESTIONS[idx];
  const correct = q.correct;
  const isCorrect = key === correct;
  answers[`${q.test_id}:${q.q_num}`] = key;
  if (isCorrect) correctCount += 1;
  document.getElementById('counter').textContent = `${correctCount}/${QUESTIONS.length} correct`;
  // Lock + colorize
  document.querySelectorAll('#opts .opt').forEach(el => {
    el.classList.add('locked');
    const k = el.dataset.key;
    if (k === correct) el.classList.add('correct');
    else if (k === key) el.classList.add('wrong');
    else el.classList.add('dim');
  });
  // Update progress dot for current question
  progressDot(idx, isCorrect ? 'done' : 'wrong');
  // Feedback panel
  const fb = document.getElementById('feedback');
  const explain = q.explanation
    ? `<div class="explain"><b>${isCorrect ? 'Correct.' : 'The answer is ' + correct + '.'}</b> ${q.explanation}</div>`
    : `<div class="explain placeholder">No baked explanation for this one. <button class="tutor-cta" id="askTutor">Ask the AI tutor →</button></div>`;
  fb.className = 'feedback show ' + (isCorrect ? 'good' : 'bad');
  fb.innerHTML = `
    <div class="row">${isCorrect ? '✓ Correct' : '✗ Missed · answer was ' + correct}</div>
    ${explain}
  `;
  const askBtn = document.getElementById('askTutor');
  if (askBtn) askBtn.addEventListener('click', () => askTutor(q));
  document.getElementById('next').classList.add('show');
}

async function askTutor(q){
  const key = `${q.test_id}:${q.q_num}`;
  const fb = document.getElementById('feedback');
  const slot = fb.querySelector('.explain');
  if (tutorCache[key]) { slot.innerHTML = tutorCache[key]; return; }
  slot.innerHTML = '<i style="color:var(--muted)">thinking…</i>';
  try {
    const res = await fetch('/api/tutor', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        test_id: q.test_id, q_num: q.q_num,
        prompt: q.prompt, options: q.options,
        correct: q.correct, user_answer: answers[key],
      })
    });
    const data = await res.json();
    if (data.error) {
      slot.innerHTML = '<i style="color:var(--red)">Tutor: ' + data.error + '</i>';
      return;
    }
    // Escape + paragraph-format the plaintext explanation from /api/tutor
    const raw = (data.explanation || 'No explanation returned.').trim();
    const safe = raw.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const html = safe.split(/\n\n+/).map(p => '<p style="margin-bottom:8px">'+p.replace(/\n/g,'<br>')+'</p>').join('');
    tutorCache[key] = html;
    slot.innerHTML = html;
  } catch (e) {
    slot.innerHTML = '<i style="color:var(--red)">Tutor error — refresh and try again.</i>';
  }
}

async function toggleBookmark(){
  const q = QUESTIONS[idx];
  const btn = document.getElementById('bm');
  try {
    // Server toggles based on current DB state; we sync the UI to whatever it returns
    const res = await fetch('/api/bookmark', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({test_id: q.test_id, q_num: q.q_num})
    });
    const data = await res.json();
    btn.classList.toggle('on', !!data.bookmarked);
    btn.textContent = data.bookmarked ? '★ Bookmarked' : '☆ Bookmark';
  } catch (e) { /* non-fatal */ }
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
  const duration = Math.round((Date.now() - startedAt) / 1000);
  try {
    const res = await fetch('/drill/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        answers: answers,
        items: QUESTIONS.map(q => ({test_id: q.test_id, q_num: q.q_num, correct: q.correct, section: q.section, topic: q.topic})),
        duration_seconds: duration,
        run_params: RUN_PARAMS,
      })
    });
    const data = await res.json();
    window.location.href = data.redirect || '/app';
  } catch (e) {
    alert('Save failed — refresh and try again.');
    document.getElementById('loading').classList.remove('show');
  }
}

render();
</script>
</body></html>
"""


EMPTY_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<title>No questions — Forma</title>
<style>body{background:#0a0805;color:#f3e7d3;font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:40px;text-align:center}
.box{max-width:480px}.box h1{font-size:24px;margin-bottom:12px}.box p{color:#8a7a5e;margin-bottom:24px}
.btn{display:inline-block;padding:11px 22px;background:#f8f1dd;color:#0a0805;font-family:ui-monospace,Menlo,monospace;font-size:12px;letter-spacing:0.1em;text-transform:uppercase;text-decoration:none}
</style></head><body><div class="box">
<h1>No questions match</h1>
<p>{{ msg }}</p>
<a class="btn" href="/app">Back to dashboard →</a>
</div></body></html>"""


DRILL_RESULT_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Drill complete — Forma</title>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0805; --panel:#15110a; --panel-2:#1e1810;
  --line:#241c11; --line-2:#36291a;
  --fg:#f3e7d3; --fg-2:#d4c5a8; --muted:#8a7a5e;
  --amber:#e8a64a; --green:#7dd87f; --red:#e87a6a; --paper:#f8f1dd;
  --sans:"Switzer",-apple-system,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
body{
  background:radial-gradient(60% 50% at 50% -5%,rgba(232,166,74,0.10),transparent 70%),
    linear-gradient(180deg,#0a0805 0%, #060402 100%);min-height:100vh;
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
  border:1px solid var(--line-2);border-radius:12px;padding:32px;background:var(--panel);
  display:grid;grid-template-columns:auto 1fr;gap:32px;margin-bottom:24px;position:relative;overflow:hidden;align-items:center;
}
.score-card::before{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--amber),transparent);opacity:0.4}
.pct-big{font-size:72px;font-weight:600;letter-spacing:-0.04em;line-height:1}
.pct-big.good{color:var(--green)}
.pct-big.mid{color:var(--amber)}
.pct-big.bad{color:var(--red)}
.score-detail .label{font-family:var(--mono);font-size:10.5px;color:var(--muted);letter-spacing:0.16em;text-transform:uppercase;margin-bottom:6px}
.score-detail .v{font-size:22px;font-weight:500;letter-spacing:-0.012em;color:var(--fg)}
.score-detail .v .sub{color:var(--muted);font-size:14px;margin-left:8px}

.topic-list{margin-bottom:36px}
.topic-list h3{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.16em;text-transform:uppercase;margin-bottom:12px}
.topic-row{display:flex;justify-content:space-between;padding:11px 14px;border:1px solid var(--line);background:var(--panel-2);margin-bottom:4px;border-radius:6px;font-size:13.5px}
.topic-row .name{color:var(--fg-2)}
.topic-row .stat{font-family:var(--mono);font-size:12px;letter-spacing:0.04em}
.topic-row .stat.good{color:var(--green)}
.topic-row .stat.bad{color:var(--red)}

.cta-row{display:flex;gap:12px;flex-wrap:wrap}
.btn-p{padding:12px 24px;background:var(--paper);color:var(--bg);font-family:var(--mono);font-size:12px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;cursor:pointer;display:inline-flex;align-items:center;gap:8px;transition:transform .1s}
.btn-p:hover{transform:translateX(2px)}
.btn-s{padding:12px 24px;background:transparent;color:var(--fg-2);font-family:var(--mono);font-size:12px;letter-spacing:0.08em;text-transform:uppercase;border:1px solid var(--line-2);display:inline-flex;align-items:center;gap:8px;transition:border-color .15s,color .15s}
.btn-s:hover{border-color:var(--amber);color:var(--amber)}
</style></head><body>

<div class="topbar">
  <a href="/" class="brand">Forma<span class="dot">●</span></a>
</div>

<div class="wrap">
  <div class="eyebrow">DRILL COMPLETE · {{ duration_min }} MIN</div>
  <h1>{{ score }} of {{ total }} correct.</h1>
  <p class="lead">{{ summary_line }}</p>

  <div class="score-card">
    <div class="pct-big {{ pct_class }}">{{ pct }}%</div>
    <div class="score-detail">
      <div class="label">Accuracy on {{ total }} questions</div>
      <div class="v">{{ score }}<span class="sub">/ {{ total }}</span></div>
    </div>
  </div>

  {% if by_topic %}
  <div class="topic-list">
    <h3>By topic</h3>
    {% for t in by_topic %}
    <div class="topic-row">
      <span class="name">{{ t.name }}</span>
      <span class="stat {% if t.pct < 60 %}bad{% elif t.pct >= 80 %}good{% endif %}">{{ t.right }}/{{ t.n }} · {{ t.pct }}%</span>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="cta-row">
    <a href="{{ next_drill_url }}" class="btn-p">Drill {{ next_drill_n }} more →</a>
    <a href="/adaptive" class="btn-s">Adaptive practice</a>
    <a href="/app" class="btn-s">Dashboard</a>
  </div>
</div>
</body></html>
"""


# ─── Route handlers ─────────────────────────────────────────────────────────
def drill_view():
    section = request.args.get("section", "math")
    topic = request.args.get("topic")
    source = request.args.get("source", "official")
    try:
        n = max(3, min(int(request.args.get("n", 10)), 25))
    except ValueError:
        n = 10

    items = _pick_questions(section=section, topic=topic, n=n, source=source)

    # Fall back to any source if official came back empty
    if len(items) < n and source != "any":
        more = _pick_questions(section=section, topic=topic, n=n - len(items), source="any")
        seen = {(i["test_id"], i["q_num"]) for i in items}
        for m in more:
            if (m["test_id"], m["q_num"]) not in seen:
                items.append(m)

    if not items:
        return render_template_string(EMPTY_HTML,
            msg=f"No drill questions found for section={section} topic={topic or '—'}.")

    if topic:
        run_label = f'<span style="color:var(--muted)">DRILLING TOPIC ·</span> {topic.upper()}'
    else:
        run_label = f'<span style="color:var(--muted)">DRILLING ·</span> {section.upper()}'

    return render_template_string(DRILL_HTML,
        questions=items,
        questions_json=json.dumps(items),
        run_params_json=json.dumps({"section": section, "topic": topic, "n": n, "source": source}),
        run_label=run_label,
    )


def drill_submit():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    answers = data.get("answers") or {}
    duration = int(data.get("duration_seconds") or 0)
    run_params = data.get("run_params") or {}

    if not items:
        return jsonify({"error": "no items"}), 400

    # Persist as attempts (one per test_id touched)
    _save_attempt(items, answers, duration)

    # Compute summary
    score = 0
    by_topic = {}
    for it in items:
        key = f"{it['test_id']}:{it['q_num']}"
        u = answers.get(key, "")
        is_c = 1 if u and u.upper() == it["correct"] else 0
        score += is_c
        t = (it.get("topic") or "").strip() or "(untagged)"
        by_topic.setdefault(t, {"n": 0, "right": 0})
        by_topic[t]["n"] += 1
        by_topic[t]["right"] += is_c
    total = len(items)
    pct = round(score * 100.0 / total) if total else 0

    # Stash in user_settings under "last_drill" so /drill/result can render it
    payload = {
        "score": score, "total": total, "pct": pct,
        "duration_seconds": duration,
        "by_topic": sorted([
            {"name": k, "n": v["n"], "right": v["right"],
             "pct": round(v["right"]*100.0/v["n"]) if v["n"] else 0}
            for k, v in by_topic.items()
        ], key=lambda r: r["pct"]),
        "run_params": run_params,
        "finished_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
                ("last_drill", json.dumps(payload)))
    conn.commit()

    return jsonify({"redirect": "/drill/result", **payload})


def drill_result():
    conn = db()
    cur = conn.cursor()
    row = cur.execute("SELECT value FROM user_settings WHERE key='last_drill'").fetchone()
    if not row:
        return redirect("/app")
    p = json.loads(row["value"])
    pct = p.get("pct", 0)
    pct_class = "good" if pct >= 75 else ("mid" if pct >= 50 else "bad")
    duration_min = max(1, round(p.get("duration_seconds", 0) / 60))
    score = p.get("score", 0)
    total = p.get("total", 0)
    # Summary line
    if pct >= 90:
        summary = "Crushed it. Want a harder set?"
    elif pct >= 70:
        summary = "Solid run. The misses below are where to focus next."
    elif pct >= 50:
        summary = "On the line. Drilling the weakest topic below will move the needle fastest."
    else:
        summary = "Rough round. The good news: every miss tells us exactly what to drill next."
    # Build "drill more" URL — reuse run_params
    rp = p.get("run_params") or {}
    params = []
    if rp.get("topic"): params.append(f"topic={rp['topic']}")
    elif rp.get("section"): params.append(f"section={rp['section']}")
    params.append(f"n={rp.get('n') or 10}")
    if rp.get("source"): params.append(f"source={rp['source']}")
    next_url = "/drill?" + "&".join(params)
    return render_template_string(DRILL_RESULT_HTML,
        score=score, total=total, pct=pct, pct_class=pct_class,
        duration_min=duration_min, by_topic=p.get("by_topic") or [],
        summary_line=summary,
        next_drill_url=next_url, next_drill_n=rp.get("n") or 10,
    )


def adaptive_drill_alias():
    """Aliases /adaptive/drill?topic=X → /drill?topic=X for the existing
    Adaptive page CTA that linked to a never-built route."""
    q = request.query_string.decode("utf-8")
    return redirect("/drill" + (f"?{q}" if q else "?section=math"))


def register(app):
    app.add_url_rule("/drill", "drill_view", drill_view)
    app.add_url_rule("/drill/submit", "drill_submit", drill_submit, methods=["POST"])
    app.add_url_rule("/drill/result", "drill_result", drill_result)
    app.add_url_rule("/adaptive/drill", "adaptive_drill", adaptive_drill_alias)
