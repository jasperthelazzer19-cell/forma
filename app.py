"""Forma — ACT prep, methodically.

Entrypoint. Most of the actual code lives in:
  forma/shell.py   — UI templates + colors + fonts
  forma/db.py      — SQLite helpers + first-boot seeding
  forma/landing.py — public landing pages (/v1…/v5)
  features.py      — dashboard / review / adaptive / library / discover / api routes

This file holds the home page (/), section drilling (/section/<sec>), test
viewer (/test/<id>), and official-forms list (/official).

Run:  python3 app.py [--port 5574]
"""
import argparse
import json
import os
from flask import Flask, g, render_template_string, redirect, url_for, request, abort, jsonify

from forma.shell import BASE_CSS, HEAD, SIDEBAR_TMPL, PALETTE_HTML, SECTION_LABELS, shell_sidebar
from forma.db import DB_PATH, db, close_db, seed_if_needed, repair_fts
from forma import explanations as expl_mod
from forma import landing
from forma import diagnostic
from forma import drill
import features

seed_if_needed()
repair_fts()

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
# Stable secret key from env (random fallback) so sessions survive restarts if added.
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24).hex()
app.teardown_appcontext(close_db)


@app.errorhandler(404)
def _not_found(e):
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Not found · Forma</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0a0805;color:#e8e3d8;font-family:system-ui,sans-serif;text-align:center}
a{color:#e8a33d;text-decoration:none}h1{font-size:3rem;margin:0 0 .2em;font-family:Georgia,serif}</style>
</head><body><div><h1>404</h1><p>That page or test doesn't exist.</p>
<p><a href="/">← Back to Forma</a></p></div></body></html>""", 404)

# ─── Base CSS shared by every page (Linear-dark app-shell) ─────────

def section_counts():
    cur = db().cursor()
    out = {}
    for k in ("english","math","reading","science"):
        cur.execute("SELECT COUNT(*) FROM tests WHERE section=?", (k,))
        out[k] = cur.fetchone()[0]
    return out

# ─── Home: section tiles ───────────────────────────────────────────
HOME_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Today · Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .session-card {
    display: grid; grid-template-columns: repeat(4, 1fr) auto; gap: 22px;
    align-items: center;
    padding: 20px 22px;
  }
  @media (max-width: 900px) { .session-card { grid-template-columns: repeat(2, 1fr); } .session-card .btn { grid-column: 1/-1; justify-self: stretch; justify-content: center; } }
  .stat-mini .n { font-family: var(--mono); font-size: 26px; font-weight: 500; letter-spacing: -0.02em; line-height: 1.1; }
  .stat-mini .n.good { color: var(--green); }
  .stat-mini .n.warn { color: var(--amber); }
  .stat-mini .n.bad { color: var(--bad); }
  .stat-mini .n.accent { color: var(--accent); }
  .stat-mini .l { font-size: 10.5px; color: var(--muted); margin-top: 5px; letter-spacing: 0.06em; }
  .stat-mini .d { font-size: 10.5px; color: var(--dim); font-family: var(--mono); margin-top: 2px; }
  .feed-label {
    font-size: 10px; color: var(--dim); letter-spacing: 0.18em;
    text-transform: uppercase; font-weight: 600; margin: 22px 0 8px;
  }
  .feed-item {
    display: grid; grid-template-columns: 28px 1fr auto; gap: 14px; align-items: center;
    padding: 12px 14px; border: 1px solid var(--border); border-radius: 6px;
    margin-bottom: 6px; background: var(--panel); text-decoration: none;
    color: var(--fg); transition: border-color .12s, background .12s;
  }
  .feed-item:hover { border-color: var(--border-strong); background: var(--panel-2); color: var(--fg); text-decoration: none; }
  .feed-ic {
    width: 28px; height: 28px; border-radius: 6px;
    background: var(--panel-2); display: flex; align-items: center; justify-content: center;
    font-size: 13px; color: var(--accent); flex-shrink: 0;
  }
  .feed-body .t { font-weight: 500; font-size: 13.5px; }
  .feed-body .d { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .feed-meta { color: var(--dim); font-size: 11.5px; font-family: var(--mono); text-align: right; }
  .feed-meta .badge {
    display: inline-block; padding: 2px 7px; border-radius: 4px;
    background: var(--accent-soft); color: var(--accent);
    font-size: 9.5px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 4px;
  }
  .feed-meta .badge.t-teal   { background: rgba(94,234,212,0.10); color: var(--teal); }
  .feed-meta .badge.t-amber  { background: rgba(251,191,36,0.10); color: var(--amber); }
  .feed-meta .badge.t-red    { background: rgba(248,113,113,0.10); color: var(--bad); }
  .feed-meta .badge.t-green  { background: rgba(74,222,128,0.10); color: var(--green); }

  .row { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; margin-top: 18px; }
  @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
  table.recent { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 12px; }
  table.recent th { text-align: left; padding: 8px 10px; color: var(--dim); font-weight: 500; border-bottom: 1px solid var(--border); letter-spacing: 0.08em; text-transform: uppercase; font-size: 9.5px; }
  table.recent td { padding: 9px 10px; border-bottom: 1px solid var(--border); color: var(--muted); }
  table.recent tr:last-child td { border-bottom: 0; }
  table.recent td.pct { font-weight: 500; }
  table.recent td.pct.good { color: var(--green); }
  table.recent td.pct.mid  { color: var(--amber); }
  table.recent td.pct.bad  { color: var(--bad); }
  table.recent td.title a { color: var(--fg); }
  table.recent td.title a:hover { color: var(--accent); }
  .recent-empty { color: var(--muted); padding: 28px; text-align: center; font-size: 13px; }
  .spark-card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .spark-card .sn { font-family: var(--mono); font-size: 18px; font-weight: 500; margin-bottom: 4px; color: var(--fg); }
  .spark-card .sl { font-size: 11.5px; color: var(--muted); }
  .spark { width: 100%; height: 56px; margin-top: 10px; }

  .empty-state {
    border: 1px dashed var(--border-strong); border-radius: 10px;
    padding: 36px 30px; text-align: center; color: var(--muted);
    background: var(--panel);
  }
  .empty-state h3 { font-family: var(--sans); font-weight: 600; font-size: 15px; color: var(--fg); margin-bottom: 6px; }
  .empty-state p { font-size: 13px; max-width: 50ch; margin: 0 auto 18px; }

  /* Diagnostic CTA banner — shows when user hasn't taken diagnostic AND has no attempts */
  .diag-banner {
    display: grid; grid-template-columns: 1fr auto; gap: 18px; align-items: center;
    padding: 22px 26px; margin: 18px 0 8px;
    background: linear-gradient(135deg, rgba(232,166,74,0.10) 0%, rgba(232,166,74,0.03) 100%);
    border: 1px solid rgba(232,166,74,0.28);
    border-radius: 12px;
    position: relative; overflow: hidden;
  }
  .diag-banner::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent); opacity: 0.6;
  }
  .diag-banner .label {
    font-family: var(--mono); font-size: 10.5px; color: var(--accent);
    letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px; font-weight: 600;
  }
  .diag-banner h3 {
    font-family: var(--sans); font-size: 17px; font-weight: 600; color: var(--fg);
    letter-spacing: -0.012em; margin-bottom: 4px;
  }
  .diag-banner p { font-size: 13.5px; color: var(--muted); max-width: 60ch; line-height: 1.5; }
  .diag-banner .btn-row { display: flex; gap: 10px; align-items: center; }
  .diag-banner .skip { font-family: var(--mono); font-size: 10.5px; color: var(--dim); letter-spacing: 0.1em; text-transform: uppercase; cursor: pointer; }
  .diag-banner .skip:hover { color: var(--muted); }
  @media (max-width: 760px) { .diag-banner { grid-template-columns: 1fr; } .diag-banner .btn-row { justify-content: flex-start; } }
</style></head><body>
<div class="app">
{{ sidebar|safe }}
<main class="main">
  <header class="topbar">
    <div class="crumbs"><b>Today</b><span class="sep">·</span>{{ total_tests }} drills available</div>
    <div class="top-actions">
      <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
      <a class="btn" href="/section/english">Start a session</a>
    </div>
  </header>
  <div class="canvas">
    <h1>{% if attempt_count == 0 %}Welcome to Forma.{% else %}Welcome back.{% endif %}</h1>
    <p class="subtitle">{% if attempt_count == 0 %}You haven't taken a drill yet. One English drill is about nine minutes.{% else %}{{ today_q }} {{ 'question' if today_q == 1 else 'questions' }} today · {{ today_pct }}% accuracy · {{ streak }}-day streak.{% endif %}</p>

    {% if not diag.taken and attempt_count == 0 %}
    <div class="diag-banner">
      <div>
        <div class="label">START HERE · 60 SECONDS</div>
        <h3>Take a 5-question warm-up to seed your dashboard.</h3>
        <p>Real official ACT math questions. We score them and project an ACT score so you have a baseline to move against. Skip if you want to dive straight in.</p>
      </div>
      <div class="btn-row">
        <a class="btn lg" href="/diagnostic">Start warm-up →</a>
      </div>
    </div>
    {% endif %}

    <div class="card session-card">
      <div class="stat-mini"><div class="n">{{ today_q }}</div><div class="l">QUESTIONS TODAY</div><div class="d">{% if attempt_count %}+{{ today_q }} from yesterday{% else %}none yet{% endif %}</div></div>
      <div class="stat-mini"><div class="n {% if today_pct >= 75 %}good{% elif today_pct >= 50 %}warn{% else %}bad{% endif %}">{{ today_pct }}%</div><div class="l">ACCURACY</div><div class="d">{% if attempt_count %}today's sessions{% else %}awaiting first run{% endif %}</div></div>
      <div class="stat-mini"><div class="n good">{{ streak }}</div><div class="l">DAY STREAK</div><div class="d">{% if streak > 0 %}keep it going{% else %}start one today{% endif %}</div></div>
      <div class="stat-mini"><div class="n accent">{% if projected %}{{ projected }}{% elif diag.taken and diag.result %}{{ diag.result.projected_math }}{% else %}—{% endif %}</div><div class="l">PROJECTED ACT</div><div class="d">{% if projected %}across sections{% elif diag.taken and diag.result %}diagnostic only · ±3{% else %}take the warm-up{% endif %}</div></div>
      <a class="btn lg" href="/section/english">Start session →</a>
    </div>

    <div class="feed-label">Suggested next</div>
    <a class="feed-item" href="/drill?section=math&n=10">
      <div class="feed-ic">⚡</div>
      <div class="feed-body"><div class="t">Quick drill — 10 math questions</div><div class="d">One at a time, instant feedback, no timer. ~6 min.</div></div>
      <div class="feed-meta"><span class="badge">Drill</span><div>~6 min</div></div>
    </a>
    {% if last_attempt %}
    <a class="feed-item" href="/test/{{ last_attempt.test_id }}">
      <div class="feed-ic">↻</div>
      <div class="feed-body">
        <div class="t">Continue where you left off</div>
        <div class="d">{{ last_attempt.title }} — last scored {{ last_attempt.pct }}% {{ last_attempt.when }}</div>
      </div>
      <div class="feed-meta"><span class="badge">Resume</span><div>~{{ last_attempt.minutes }} min</div></div>
    </a>
    {% endif %}
    {% if weakest_topic %}
    <a class="feed-item" href="/test/{{ weakest_topic.test_id }}">
      <div class="feed-ic">◎</div>
      <div class="feed-body">
        <div class="t">Drill your weakest topic: {{ weakest_topic.name }}</div>
        <div class="d">{{ weakest_topic.pct }}% accuracy across {{ weakest_topic.attempted }} attempts — {{ weakest_topic.qcount }} q in this bank</div>
      </div>
      <div class="feed-meta"><span class="badge">Adaptive</span><div>~9 min</div></div>
    </a>
    {% else %}
    <a class="feed-item" href="/adaptive">
      <div class="feed-ic">◎</div>
      <div class="feed-body"><div class="t">Drill your weakest topics</div><div class="d">Adaptive picks 15 questions from where you're scoring lowest</div></div>
      <div class="feed-meta"><span class="badge">Adaptive</span><div>~9 min</div></div>
    </a>
    {% endif %}
    {% if wrong_count and wrong_count > 0 %}
    <a class="feed-item" href="/review">
      <div class="feed-ic">⟳</div>
      <div class="feed-body">
        <div class="t">Review wrong answers</div>
        <div class="d">{{ wrong_count }} question{% if wrong_count != 1 %}s{% endif %} you've missed, most recent first</div>
      </div>
      <div class="feed-meta"><span class="badge t-red">Review</span><div>~{{ (wrong_count * 25 / 60)|round|int }} min</div></div>
    </a>
    {% endif %}
    <a class="feed-item" href="/full-test">
      <div class="feed-ic">⏱</div>
      <div class="feed-body"><div class="t">Take a full timed test</div><div class="d">{% if official_count %}{{ official_count }} official forms + {{ gen_count }} AI-generated{% else %}Real ACT timing across all four sections{% endif %}</div></div>
      <div class="feed-meta"><span class="badge t-teal">Full</span><div>~3 hr</div></div>
    </a>
    <a class="feed-item" href="/topics">
      <div class="feed-ic">◆</div>
      <div class="feed-body"><div class="t">Browse topic banks</div><div class="d">69 topic-tagged drills across all four sections — pick a specific concept</div></div>
      <div class="feed-meta"><span class="badge t-amber">Topics</span><div>10-15 min each</div></div>
    </a>

    <div class="row">
      <div>
        <div class="feed-label">Recent attempts</div>
        <div class="card" style="padding:0">
        {% if recent %}
          <table class="recent">
            <tr><th>WHEN</th><th>TEST</th><th>SECTION</th><th style="text-align:right">SCORE</th></tr>
            {% for r in recent %}
            <tr>
              <td>{{ r.when }}</td>
              <td class="title"><a href="/test/{{ r.test_id }}">{{ r.title }}</a></td>
              <td>{{ r.section|title }}</td>
              <td class="pct {{ r.cls }}" style="text-align:right">{{ r.score }}/{{ r.total }} · {{ r.pct }}%</td>
            </tr>
            {% endfor %}
          </table>
        {% else %}
          <div class="recent-empty">No attempts yet. Pick anything from the sidebar — your first drill takes about nine minutes.</div>
        {% endif %}
        </div>
      </div>
      <div>
        <div class="feed-label">Library</div>
        <div class="spark-card">
          <div class="sn">{{ total_tests }} drills</div>
          <div class="sl">{{ total_questions }} questions · {{ official_count or 0 }} official forms · {{ gen_count or 0 }} AI-generated</div>
          <svg class="spark" viewBox="0 0 200 56" preserveAspectRatio="none">
            <polyline points="0,40 28,35 56,30 84,32 112,22 140,18 168,20 196,12"
              fill="none" stroke="#e8a64a" stroke-width="1.5" />
            <polyline points="0,40 28,35 56,30 84,32 112,22 140,18 168,20 196,12 196,56 0,56"
              fill="rgba(232,166,74,0.08)" stroke="none" />
          </svg>
        </div>
        <div class="spark-card" style="margin-top:10px">
          <div class="sn" style="color:var(--muted);font-size:13.5px">Last scraped {{ last_scraped or 'never' }}</div>
          <div class="sl">Inventory <span class="mono">forma · v1</span></div>
        </div>
      </div>
    </div>
  </div>
</main>
</div>
{{ palette|safe }}
</body></html>
"""

@app.route("/app")
def home():
    cur = db().cursor()
    # Total attempts → drives onboarding empty-state
    cur.execute("SELECT COUNT(*) FROM attempts")
    attempt_count = cur.fetchone()[0]
    # Today's activity for the widget
    cur.execute("""SELECT COUNT(*), AVG(pct) FROM attempts
                   WHERE date(started_at) = date('now')""")
    row = cur.fetchone()
    today_q = row[0] or 0
    today_pct = round(row[1] or 0, 0)
    # Streak: consecutive days back from today with at least 1 attempt
    cur.execute("SELECT DISTINCT date(started_at) FROM attempts ORDER BY 1 DESC")
    dates = [r[0] for r in cur.fetchall()]
    streak = 0
    if dates:
        from datetime import datetime as _dt
        cur_date = _dt.utcnow().date()
        date_set = set(dates)
        while cur_date.isoformat() in date_set:
            streak += 1
            cur_date = _dt.fromordinal(cur_date.toordinal() - 1)
    sections = []
    total_t, total_q = 0, 0
    for key, label in SECTION_LABELS.items():
        cur.execute("SELECT COUNT(*) FROM tests WHERE section = ?", (key,))
        tc = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM questions q JOIN tests t ON q.test_id = t.id WHERE t.section = ?", (key,))
        qc = cur.fetchone()[0]
        total_t += tc; total_q += qc
        minutes = {"english": 9, "math": 15, "reading": 9, "science": 9}.get(key, 10)
        sections.append({"key": key, "label": label, "count": tc, "qcount": qc, "minutes": minutes})
    cur.execute("SELECT MAX(scraped_at) FROM tests")
    last = cur.fetchone()[0]
    # Count of official forms (separate tab)
    cur.execute("SELECT COUNT(DISTINCT form_code) FROM tests WHERE source='official'")
    official_count = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(DISTINCT form_code) FROM tests WHERE source='generated'")
    gen_count = cur.fetchone()[0] or 0
    # Recent attempts (last 6) for the Today panel
    cur.execute("""SELECT a.id, a.test_id, a.score, a.total, a.pct, a.started_at,
                          t.title, t.section
                   FROM attempts a LEFT JOIN tests t ON t.id = a.test_id
                   ORDER BY a.started_at DESC LIMIT 6""")
    recent = []
    for r in cur.fetchall():
        pct = round(r["pct"] or 0, 0)
        cls = "good" if pct >= 75 else ("mid" if pct >= 50 else "bad")
        try:
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(r["started_at"])
            when = dt.strftime("%b %-d")
        except Exception:
            when = (r["started_at"] or "")[:10]
        recent.append({
            "test_id": r["test_id"], "title": (r["title"] or "—")[:42],
            "section": r["section"] or "—", "score": int(r["score"] or 0),
            "total": int(r["total"] or 0), "pct": int(pct), "cls": cls, "when": when,
        })
    # Projected composite from features.predict_score
    cur.execute("""SELECT t.section AS sec, SUM(a.total) AS total_q, SUM(a.score) AS right_q
                   FROM attempts a JOIN tests t ON t.id = a.test_id
                   GROUP BY t.section""")
    pct_by_sec = {}
    for r in cur.fetchall():
        if (r["total_q"] or 0) > 0:
            pct_by_sec[r["sec"]] = (r["right_q"] or 0) / r["total_q"] * 100
    projected = None
    if pct_by_sec:
        from features import predict_score
        projected, _ = predict_score(pct_by_sec)
    # Last attempt for "continue where you left off"
    last_attempt = None
    cur.execute("""SELECT a.test_id, a.pct, a.started_at, t.title, t.section
                   FROM attempts a JOIN tests t ON t.id=a.test_id
                   ORDER BY a.started_at DESC LIMIT 1""")
    la = cur.fetchone()
    if la:
        from datetime import datetime as _dt
        try:
            dt = _dt.fromisoformat(la["started_at"])
            delta = (_dt.utcnow() - dt).total_seconds()
            if delta < 3600: when = "less than an hour ago"
            elif delta < 86400: when = f"{int(delta/3600)}h ago"
            elif delta < 86400*7: when = f"{int(delta/86400)}d ago"
            else: when = dt.strftime("on %b %-d")
        except Exception:
            when = "recently"
        minutes_map = {"english": 9, "math": 15, "reading": 9, "science": 9}
        last_attempt = {
            "test_id": la["test_id"],
            "title": (la["title"] or "—")[:50],
            "pct": int(round(la["pct"] or 0)),
            "when": when,
            "minutes": minutes_map.get(la["section"], 10),
        }
    # Weakest topic (for the suggested-next feed)
    weakest_topic = None
    cur.execute("""SELECT t.id AS test_id, t.topic AS slug, t.section,
                          (SELECT COUNT(*) FROM questions WHERE test_id=t.id) AS qcount,
                          (SELECT COUNT(*) FROM attempt_answers aa JOIN attempts a ON a.id=aa.attempt_id WHERE a.test_id=t.id) AS attempted,
                          (SELECT AVG(aa.is_correct)*100 FROM attempt_answers aa JOIN attempts a ON a.id=aa.attempt_id WHERE a.test_id=t.id) AS pct
                   FROM tests t WHERE t.source='varsity' AND t.topic IS NOT NULL""")
    candidates = []
    for r in cur.fetchall():
        if (r["attempted"] or 0) >= 5 and (r["pct"] or 0) > 0:
            candidates.append(r)
    if candidates:
        candidates.sort(key=lambda r: r["pct"] or 100)
        w = candidates[0]
        weakest_topic = {
            "test_id": w["test_id"],
            "name": (w["slug"] or "").replace("-", " ").title(),
            "pct": int(round(w["pct"] or 0)),
            "attempted": int(w["attempted"] or 0),
            "qcount": int(w["qcount"] or 0),
        }
    # Wrong-answer count
    cur.execute("SELECT COUNT(*) FROM attempt_answers WHERE is_correct = 0")
    wrong_count = cur.fetchone()[0] or 0
    # Diagnostic status — drives the START HERE banner + seeds projected ACT
    diag = diagnostic.diagnostic_status()
    return render_template_string(
        HOME_HTML,
        base_css=BASE_CSS, sections=sections,
        sidebar=shell_sidebar("home", section_counts()),
        palette=PALETTE_HTML,
        total_tests=total_t, total_questions=total_q,
        last_scraped=last,
        official_count=official_count, gen_count=gen_count,
        attempt_count=attempt_count,
        today_q=today_q, today_pct=today_pct, streak=streak,
        recent=recent, projected=projected,
        last_attempt=last_attempt, weakest_topic=weakest_topic, wrong_count=wrong_count,
        diag=diag,
    )

# ─── Section: list of tests ────────────────────────────────────────
SECTION_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>{{ section_label }} — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .test-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin-top: 14px; }
  .test-tile {
    display: flex; align-items: center; justify-content: center;
    padding: 16px 12px; text-align: center;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 7px; text-decoration: none; color: var(--fg);
    font-family: var(--mono); font-size: 13px; letter-spacing: 0.02em;
    transition: border-color .12s, background .12s;
  }
  .test-tile .num { font-family: var(--mono); font-size: 18px; font-weight: 500; letter-spacing: -0.01em; color: var(--fg); }
  .test-tile small { color: var(--dim); font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; display: block; margin-top: 4px; }
  .test-tile:hover {
    border-color: var(--accent-dim); color: var(--fg);
    background: var(--panel-2);
    text-decoration: none;
  }
  .filter { margin: 14px 0 0; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .filter input {
    background: var(--panel); border: 1px solid var(--border-strong);
    color: var(--fg); padding: 7px 12px; border-radius: 6px;
    font-family: var(--sans); font-size: 12.5px; min-width: 220px;
    outline: none; transition: border-color .12s;
  }
  .filter input:focus { border-color: var(--accent); }
  .filter a {
    padding: 7px 12px; border-radius: 6px; border: 1px solid var(--border-strong);
    color: var(--muted); font-size: 11.5px; font-weight: 500; text-decoration: none;
    transition: color .12s, border-color .12s;
  }
  .filter a:hover { border-color: var(--accent); color: var(--fg); text-decoration: none; }
</style></head><body>
<div class="app">
{{ sidebar|safe }}
<main class="main">
<header class="topbar">
  <div class="crumbs"><a href="/app" style="color:var(--muted)">Workspace</a><span class="sep">▸</span><b>{{ section_label }}</b></div>
  <div class="top-actions">
    <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
  </div>
</header>
<div class="canvas">
  <div class="eyebrow">{{ section_label }}</div>
  <h1>{{ count }} {{ section_label }} practice tests</h1>
  <p class="muted">Pick one. Each test = ~{{ qpt }} questions, ~{{ minutes }} min if you time yourself.</p>

  <div class="filter">
    <input id="q" type="search" placeholder="Filter… (e.g. 5, 'test301')" oninput="filter()">
    <a href="javascript:goRandom()">🎲 Random</a>
  </div>

  {% set full_tests = tests | selectattr('kind', 'in', ['official', 'generated']) | list %}
  {% set drills = tests | selectattr('kind', 'equalto', 'drill') | list %}
  {% set varsity = tests | selectattr('kind', 'equalto', 'varsity') | list %}
  {% if full_tests %}
    <div class="sub-header">
      <h3>Full-length tests</h3>
      <span class="ct">{{ full_tests|length }} forms</span>
    </div>
    <div class="test-list" id="full-list">
      {% for t in full_tests %}
      <a class="test-tile tile-{{ t.kind }}" data-key="{{ t.display_num }} {{ t.kind }}" href="/test/{{ t.id }}">
        <div>
          <div class="num" style="font-size: 16px">{{ t.display_num }}</div>
          <small>
            {% if t.kind == 'official' %}{{ t.qcount }} Q · OFFICIAL
            {% else %}{{ t.qcount }} Q · AI FULL{% endif %}
          </small>
        </div>
      </a>
      {% endfor %}
    </div>
  {% endif %}
  {% set good_drills = drills | rejectattr('fragmented') | list %}
  <div class="sub-header" style="margin-top: 32px">
    <h3>Practice drills (15-q chunks)</h3>
    <span class="ct">{{ good_drills|length }} drills</span>
  </div>
  <div class="test-list" id="list">
    {% for t in good_drills %}
    <a class="test-tile tile-{{ t.kind }}" data-key="{{ t.display_num }} test{{ t.display_num }} {{ t.kind }}" href="/test/{{ t.id }}">
      <div>
        <div class="num">{{ t.display_num }}</div>
        <small>{{ t.qcount }} Q</small>
      </div>
    </a>
    {% endfor %}
  </div>
  {% if varsity %}
    <div class="sub-header" style="margin-top: 32px">
      <h3>Topic banks · Varsity Tutors</h3>
      <span class="ct">{{ varsity|length }} topics · {{ varsity|sum(attribute='qcount') }} q</span>
    </div>
    <div class="test-list" id="varsity-list" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));">
      {% for t in varsity %}
      <a class="test-tile tile-varsity" data-key="{{ t.display_num|lower }} varsity {{ t.topic|default('') }}" href="/test/{{ t.id }}" style="text-align:left;padding:14px 16px">
        <div style="width:100%">
          <div class="num" style="font-size:13px;font-weight:500;line-height:1.3;color:var(--fg)">{{ t.display_num }}</div>
          <small style="margin-top:6px">{{ t.qcount }} q · explanations</small>
        </div>
      </a>
      {% endfor %}
    </div>
  {% endif %}
  {% set frag_drills = drills | selectattr('fragmented') | list %}
  {% if frag_drills %}
    <details class="frag-section">
      <summary>▸ Show {{ frag_drills|length }} drills with broken source passages</summary>
      <p class="muted" style="font-size:12px;margin:8px 0 12px">These drills' source images are fragmented — questions still work but you won't see clean passage prose.</p>
      <div class="test-list">
        {% for t in frag_drills %}
        <a class="test-tile tile-frag" data-key="{{ t.display_num }} test{{ t.display_num }}" href="/test/{{ t.id }}">
          <div>
            <div class="num">{{ t.display_num }}</div>
            <small>{{ t.qcount }} Q · BROKEN SRC</small>
          </div>
        </a>
        {% endfor %}
      </div>
    </details>
    <style>
      .frag-section { margin-top: 26px; padding: 10px 0; border-top: 1px solid rgba(255,255,255,0.05); }
      .frag-section summary {
        cursor: pointer; padding: 10px 0; color: var(--muted);
        font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase;
        list-style: none;
      }
      .frag-section summary:hover { color: var(--fg); }
      .frag-section[open] summary { color: var(--fg); }
      .test-tile.tile-frag {
        background: rgba(255,255,255,0.015); opacity: 0.65;
      }
      .test-tile.tile-frag small { color: #fbbf24 !important; font-weight: 600; }
    </style>
  {% endif %}
  <style>
    .test-tile.tile-official {
      border-color: rgba(94,234,212,0.22);
      background: linear-gradient(180deg, rgba(94,234,212,0.05) 0%, var(--bg-2) 100%);
    }
    .test-tile.tile-official:hover { border-color: var(--accent); }
    .test-tile.tile-generated {
      border-color: rgba(168,85,247,0.28);
      background: linear-gradient(180deg, rgba(168,85,247,0.05) 0%, var(--bg-2) 100%);
    }
    .test-tile.tile-generated:hover { border-color: rgba(168,85,247,0.55); }
    .test-tile small {
      font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase;
      color: var(--muted); display: block; margin-top: 4px;
    }
    .test-tile.tile-official small { color: var(--accent); }
    .test-tile.tile-generated small { color: #c4a4ff; }
    .sub-header {
      display: flex; align-items: baseline; justify-content: space-between;
      margin: 24px 0 4px;
    }
    .sub-header h3 {
      font-family: var(--sans); font-weight: 600; font-size: 13px;
      color: var(--fg); letter-spacing: -0.004em;
    }
    .sub-header .ct {
      font-size: 10px; color: var(--dim);
      letter-spacing: 0.16em; text-transform: uppercase; font-weight: 600;
    }
    .test-tile.tile-official {
      border-left: 2px solid var(--teal);
    }
    .test-tile.tile-official:hover { border-color: var(--teal); }
    .test-tile.tile-generated {
      border-left: 2px solid var(--accent);
    }
    .test-tile.tile-generated:hover { border-color: var(--accent); }
    .test-tile.tile-varsity {
      border-left: 2px solid #f59e0b;
      align-items: stretch; justify-content: flex-start;
    }
    .test-tile.tile-varsity:hover { border-color: #f59e0b; }
    .test-tile.tile-varsity small { color: #f59e0b !important; }
  </style>
</div>
</main>
</div>
{{ palette|safe }}
<script>
function filter() {
  const q = document.getElementById('q').value.toLowerCase().trim();
  document.querySelectorAll('.test-tile').forEach(el => {
    el.style.display = (!q || el.dataset.key.includes(q)) ? '' : 'none';
  });
}
function goRandom() {
  const visible = [...document.querySelectorAll('.test-tile')].filter(e => e.style.display !== 'none');
  if (!visible.length) return;
  visible[Math.floor(Math.random()*visible.length)].click();
}
</script>
</body></html>
"""

@app.route("/section/<section>")
def section(section):
    if section not in SECTION_LABELS:
        abort(404)
    cur = db().cursor()
    cur.execute("""
      SELECT t.id, t.test_number, t.source, t.form_code, t.year, t.month, t.title, t.topic,
             length(t.passage_text) AS text_len,
             (length(t.passage_div_html) > 0) AS has_image,
             (SELECT COUNT(*) FROM questions WHERE test_id = t.id) AS qcount
      FROM tests t
      WHERE section = ?
      ORDER BY
        -- Full tests first (official/generated), then good drills, then fragmented drills
        CASE WHEN t.source IN ('official','generated') THEN 0
             WHEN length(t.passage_text) >= 400 OR length(t.passage_div_html) > 0 THEN 1
             ELSE 2 END,
        t.year DESC NULLS LAST,
        t.test_number IS NULL, t.test_number ASC, t.id ASC
    """, (section,))
    tests = []
    drill_num = 0
    for r in cur.fetchall():
        d = dict(r)
        # For math: no passage needed; never mark as fragmented.
        if section == "math":
            d["fragmented"] = False
        else:
            d["fragmented"] = (
                (d.get("source") or "crackab") == "crackab"
                and (d.get("text_len") or 0) < 400
            )
        src = d.get("source") or "crackab"
        if src == "crackab":
            drill_num += 1
            d["display_num"] = drill_num
            d["kind"] = "drill"
        elif src == "official":
            d["display_num"] = f"Form {d['form_code']}"
            d["kind"] = "official"
        elif src == "varsity":
            # Topic-bank from Varsity Tutors. Render topic slug as display name.
            topic = (r["title"] or "").split("—", 1)[-1].strip() or d.get("form_code") or "Topic"
            d["display_num"] = topic
            d["kind"] = "varsity"
        else:
            d["display_num"] = d.get("form_code") or "GEN"
            d["kind"] = "generated"
        tests.append(d)
    qpt = next((t["qcount"] for t in tests if t["kind"] == "drill"), 15)
    minutes = {"english": 9, "math": 15, "reading": 9, "science": 9}.get(section, 10)
    return render_template_string(
        SECTION_HTML,
        base_css=BASE_CSS,
        sidebar=shell_sidebar(section, section_counts()),
        palette=PALETTE_HTML,
        section=section, section_label=SECTION_LABELS[section],
        count=len(tests), tests=tests,
        qpt=qpt, minutes=minutes,
    )

# ─── Test page: passage + questions + client-side grading ──────────
TEST_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>{{ test.title }} — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .wrap { max-width: 1240px; }
  .test-meta {
    display: flex; gap: 0; font-size: 11px; color: var(--muted);
    margin: 0 0 22px; letter-spacing: 0.18em; text-transform: uppercase;
    font-family: var(--mono);
  }
  .test-meta span { padding: 0 16px; border-right: 1px solid var(--border); }
  .test-meta span:first-child { padding-left: 0; }
  .test-meta span:last-child { border-right: 0; }
  /* Two-column passage + questions layout */
  .test-grid {
    display: grid; grid-template-columns: 1.05fr 1fr; gap: 28px;
    align-items: start; margin-top: 18px;
  }
  @media (max-width: 980px) {
    .test-grid { grid-template-columns: 1fr; }
    /* Stacked single column on mobile: don't trap the passage in a short
       sticky scroll-box — let it flow above the questions. */
    .passage-col { position: static; max-height: none; overflow-y: visible; padding: 22px 18px; }
    .wrap { padding: 16px 16px 60px; }
  }
  .passage-col {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 36px 38px;
    line-height: 1.85;
    font-size: 15.5px;
    font-family: var(--serif);
    position: sticky; top: 92px;
    max-height: calc(100vh - 120px);
    overflow-y: auto;
    box-shadow: var(--shadow-soft);
  }
  .passage-col::after {
    content: ""; position: sticky; bottom: 0; left: 0; right: 0;
    display: block; height: 40px; margin: -40px -38px 0;
    background: linear-gradient(180deg, transparent, var(--bg-2));
    pointer-events: none;
  }
  .passage-col::-webkit-scrollbar { width: 8px; }
  .passage-col::-webkit-scrollbar-track { background: transparent; }
  .passage-col::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
  .passage-col::-webkit-scrollbar-thumb:hover { background: rgba(94,234,212,0.25); }
  .passage-col h3, .passage-col h4, .passage-col strong, .passage-col b {
    font-family: var(--serif); font-weight: 500;
    color: var(--fg); display: block; margin-bottom: 14px;
  }
  .passage-col p { margin: 0 0 1.1em; }
  .passage-col p.center { text-align: center; }
  .passage-col u, .passage-col .underline { text-decoration: underline; text-decoration-color: var(--accent); text-decoration-thickness: 1.5px; }
  .passage-col sup { color: var(--accent); font-weight: 700; padding: 0 2px; }
  .passage-col table { border-collapse: collapse; margin: 14px auto; max-width: 100%; }
  .passage-col td, .passage-col th { padding: 6px 10px; border: 1px solid rgba(255,255,255,0.10); font-size: 13.5px; }
  /* Image scans (some tests use JPG snapshots of book pages instead of text).
     Invert+hue-rotate so white book pages become dark, black text becomes light. */
  .passage-col img {
    max-width: 100%; height: auto; display: block;
    margin: 14px auto;
    border-radius: 6px;
    filter: invert(0.93) hue-rotate(180deg) saturate(0.5) contrast(1.05);
    background: transparent;
  }
  /* OCR'd passage text — plain fallback (no AI markers yet) */
  .passage-col pre.passage-text {
    font-family: var(--serif);
    font-size: 16px;
    line-height: 1.75;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: var(--fg);
    background: transparent;
    border: 0;
    padding: 0;
    margin: 0;
  }
  /* HTML-rendered marked passage (looks like printed ACT) */
  .passage-col div.passage-text {
    font-family: var(--serif);
    font-size: 16px;
    line-height: 1.8;
    color: var(--fg);
  }
  .passage-col div.passage-text p {
    margin: 0 0 1.1em 0;
  }
  /* Underlined portions: subtle teal underline to evoke the ACT print look */
  .passage-col div.passage-text u {
    text-decoration: underline;
    text-decoration-color: rgba(94, 234, 212, 0.75);
    text-decoration-thickness: 1.5px;
    text-underline-offset: 3px;
  }
  /* Subscript question numbers: small teal pill that floats just under the underline */
  .passage-col div.passage-text sub {
    color: var(--accent);
    font-family: var(--mono);
    font-size: 0.65em;
    font-weight: 700;
    margin: 0 4px 0 2px;
    vertical-align: sub;
    line-height: 0;
  }
  /* Mode toggle (Text vs Original image) */
  .passage-mode-toggle {
    display: inline-flex; gap: 0;
    background: var(--bg);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 3px;
    margin-bottom: 18px;
  }
  .passage-mode-toggle .mode-btn {
    background: transparent; border: 0; cursor: pointer;
    color: var(--muted);
    font-family: var(--mono); font-size: 10px;
    letter-spacing: 0.16em; text-transform: uppercase; font-weight: 500;
    padding: 6px 14px; border-radius: 6px;
    transition: background .12s, color .12s;
  }
  .passage-mode-toggle .mode-btn:hover { color: var(--fg); }
  .passage-mode-toggle .mode-btn.on { background: var(--accent); color: #0b1220; font-weight: 700; }
  .passage-mode.hidden { display: none; }
  /* Add real breathing room between stacked image paragraphs */
  .passage-col p.dis_img, .passage-col p.dis_imgz {
    margin: 18px 0;
    text-align: center;
  }
  .passage-empty { color: var(--muted); font-style: italic; }
  .questions-col { min-width: 0; }
  /* ─── Clean question styling — CrackAB form structure ─── */
  .passage-wrap form { display: block; }
  .passage-wrap #myquestion { padding: 0; }
  /* Hide CrackAB's hidden inputs (they show as inline blocks otherwise) */
  .passage-wrap input[type="hidden"] { display: none; }
  /* Question number/prompt: distinct visual break between questions */
  .passage-wrap p {
    margin: 28px 0 14px 0;
    color: var(--fg);
    font-size: 15px;
    line-height: 1.55;
    padding-top: 4px;
  }
  .passage-wrap p:first-child { margin-top: 0; padding-top: 0; }
  .passage-wrap p b {
    color: var(--accent);
    font-family: var(--serif);
    font-weight: 500;
    font-style: italic;
    font-size: 22px;
    margin-right: 10px;
    font-variation-settings: "opsz" 144;
    letter-spacing: -0.02em;
  }
  /* Each option (CrackAB wraps in .radio > label > input + text) */
  .passage-wrap .radio {
    margin: 6px 0;
    padding: 11px 14px;
    border-radius: 10px;
    border: 1px solid transparent;
    transition: background .18s cubic-bezier(.2,.7,.2,1),
                border-color .18s, transform .18s;
    position: relative;
  }
  .passage-wrap .radio:hover {
    background: rgba(94,234,212,0.03);
    border-color: var(--border-strong);
    transform: translateX(2px);
  }
  .passage-wrap .radio label {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    cursor: pointer;
    font-size: 14px;
    line-height: 1.5;
    color: var(--fg);
    width: 100%;
  }
  .passage-wrap input[type="radio"] {
    appearance: none;
    -webkit-appearance: none;
    width: 18px; height: 18px;
    border: 1.5px solid rgba(255,255,255,0.25);
    border-radius: 50%;
    background: transparent;
    cursor: pointer;
    margin: 0;
    flex-shrink: 0;
    transition: border-color .15s, background .15s;
    position: relative;
    top: 2px;
  }
  .passage-wrap input[type="radio"]:hover { border-color: var(--accent); }
  .passage-wrap input[type="radio"]:checked {
    border-color: var(--accent);
    background: radial-gradient(circle, var(--accent) 0, var(--accent) 5px, transparent 6px);
  }
  /* When a .radio contains the SELECTED radio, accent the whole row */
  .passage-wrap .radio:has(input:checked) {
    background: rgba(94,234,212,0.06);
    border-color: rgba(94,234,212,0.22);
  }
  /* After grading: opt-correct on a <span> we inject. Color the option text. */
  .passage-wrap span.opt-correct {
    color: var(--good);
    font-weight: 600;
  }
  .passage-wrap span.opt-wrong {
    color: var(--bad);
    text-decoration: line-through;
    text-decoration-color: rgba(248,113,113,0.5);
  }
  .timer {
    position: sticky; top: 76px; z-index: 30;
    background: linear-gradient(180deg, rgba(12,20,30,0.92), rgba(6,10,18,0.92));
    backdrop-filter: blur(12px) saturate(160%);
    -webkit-backdrop-filter: blur(12px) saturate(160%);
    padding: 12px 18px;
    border: 1px solid var(--border-strong); border-radius: 12px;
    display: inline-flex; gap: 18px; align-items: center;
    font-size: 13px; font-variant-numeric: tabular-nums;
    box-shadow: var(--shadow-soft);
  }
  .timer::before {
    content: ""; width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 14px var(--accent);
    animation: pulse-dot 2.2s ease-in-out infinite;
  }
  @keyframes pulse-dot {
    0%, 100% { opacity: 0.4; transform: scale(0.85); }
    50% { opacity: 1; transform: scale(1.1); }
  }
  .timer .t {
    color: var(--fg); font-weight: 600;
    font-family: var(--mono); letter-spacing: 0.08em;
    font-size: 15px;
  }
  .timer button {
    background: transparent; border: 0; color: var(--muted);
    cursor: pointer; font-family: var(--mono); font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.20em;
    padding: 4px 0; transition: color .15s;
  }
  .timer button:hover { color: var(--accent); }
  .passage-wrap {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px 34px;
    margin: 0;
    line-height: 1.7;
    font-size: 14.5px;
    box-shadow: var(--shadow-soft);
  }
  /* Per-question explanation panel */
  .q-explain {
    margin: 4px 0 16px 0;
    padding: 0;
    background: transparent;
    font-size: 12.5px;
  }
  .q-explain summary {
    cursor: pointer; color: var(--muted);
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
    padding: 4px 0; user-select: none;
  }
  .q-explain summary::marker { color: var(--accent); }
  .q-explain summary:hover { color: var(--accent); }
  .q-explain[open] summary { color: var(--accent); }
  .q-explain .panel {
    margin-top: 8px;
    padding: 14px 16px;
    background: rgba(94,234,212,0.04);
    border-left: 2px solid var(--accent);
    border-radius: 0 6px 6px 0;
    line-height: 1.65;
    color: var(--fg);
  }
  .q-explain .panel strong, .q-explain .panel b { color: var(--accent); }
  .q-explain .panel p { margin: 0 0 0.6em; }
  .q-explain .panel .loading { color: var(--muted); font-style: italic; }
  /* normalize the original CrackAB-injected markup to match the dark theme */
  .passage-wrap p { margin: 0 0 1.1em; }
  .passage-wrap h3, .passage-wrap h4, .passage-wrap h5, .passage-wrap b {
    color: var(--fg); font-family: var(--serif); font-weight: 500;
  }
  .passage-wrap ul, .passage-wrap ol { margin-left: 24px; }
  .passage-wrap u { text-decoration: underline; text-decoration-color: var(--accent); text-decoration-thickness: 1.5px; }
  .passage-wrap a { color: var(--muted); pointer-events: none; }
  .passage-wrap table { border-collapse: collapse; margin: 12px 0; }
  .passage-wrap td, .passage-wrap th { padding: 6px 10px; border: 1px solid rgba(255,255,255,0.08); }
  /* hide CrackAB's own submit button and any meta lists they include */
  .passage-wrap input[type="submit"], .passage-wrap button[type="submit"] { display: none !important; }
  .passage-wrap input[type="hidden"] { display: none; }
  /* Style the embedded radio inputs cleanly */
  .passage-wrap input[type="radio"] {
    accent-color: var(--accent);
    margin-right: 6px;
    transform: translateY(2px);
  }
  .passage-wrap label, .passage-wrap input[type="radio"] + * { cursor: pointer; }
  /* radio option states after grading */
  .passage-wrap .opt-correct { color: var(--good); font-weight: 600; }
  .passage-wrap .opt-wrong   { color: var(--bad);  text-decoration: line-through; }
  .controls { display: flex; gap: 12px; margin: 20px 0 30px; }
  .results {
    display: none;
    background:
      linear-gradient(180deg, rgba(94,234,212,0.05), transparent 40%),
      linear-gradient(180deg, var(--bg-3), var(--bg-2));
    border: 1px solid var(--border-strong);
    border-radius: 16px;
    padding: 26px 28px;
    margin: 0 0 32px;
    box-shadow: var(--shadow-deep);
    position: relative; overflow: hidden;
  }
  .results::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent) 50%, transparent);
    opacity: 0.6;
  }
  @keyframes results-rise {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .results.show { display: block; animation: results-rise .4s cubic-bezier(.2,.7,.2,1) both; }
  .results .score {
    font-family: var(--serif); font-size: 56px; font-weight: 600;
    color: var(--fg); letter-spacing: -0.034em; line-height: 1;
    font-variation-settings: "opsz" 144;
  }
  .results .score em {
    font-style: italic; color: var(--accent); font-weight: 600;
  }
  .results .breakdown {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(54px,1fr));
    gap: 6px; margin-top: 22px;
    padding-top: 22px; border-top: 1px solid var(--border);
  }
  .results .qcell {
    text-align: center; padding: 10px 4px; border-radius: 8px;
    font-size: 12px; font-variant-numeric: tabular-nums; letter-spacing: 0.04em;
    transition: transform .15s;
  }
  .results .qcell:hover { transform: translateY(-2px); }
  .qcell.right { background: rgba(94,234,212,0.10); color: var(--good); border: 1px solid rgba(94,234,212,0.28); }
  .qcell.wrong { background: rgba(248,113,113,0.08); color: var(--bad);  border: 1px solid rgba(248,113,113,0.28); }
  .qcell.blank { background: rgba(255,255,255,0.03); color: var(--muted); border: 1px solid var(--border); }
  .qcell .ans { display: block; font-weight: 700; font-size: 15px; line-height: 1.1; font-family: var(--mono); }
  .qcell .num { display: block; font-size: 9.5px; opacity: 0.6; letter-spacing: 0.12em; margin-bottom: 3px; }
  .nav-row { display: flex; justify-content: space-between; margin-top: 30px; padding-top: 22px; border-top: 1px solid rgba(255,255,255,0.06); }
  /* Keyboard-focus glow on current question */
  .kb-focus {
    position: relative;
  }
  .kb-focus::before {
    content: ""; position: absolute; inset: -8px -14px; border-radius: 10px;
    background: var(--accent-soft); pointer-events: none;
    box-shadow: 0 0 0 1px var(--accent-dim) inset;
    z-index: -1;
  }
  /* Shortcut overlay */
  #kb-help {
    position: fixed; inset: 0; z-index: 200;
    background: rgba(0,0,0,0.55); backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
  }
  #kb-help .kb-help-card {
    background: var(--panel); border: 1px solid var(--border-strong);
    border-radius: 12px; padding: 24px 30px; min-width: 320px;
    box-shadow: 0 30px 80px rgba(0,0,0,0.6);
  }
  #kb-help h3 {
    font-family: var(--sans); font-size: 14px; font-weight: 600;
    color: var(--fg); margin-bottom: 16px; letter-spacing: -0.004em;
  }
  #kb-help .kb-row {
    display: flex; align-items: center; gap: 14px;
    padding: 6px 0; font-size: 13px; color: var(--muted);
  }
  #kb-help .kb-row .kb {
    font-family: var(--mono); font-size: 10.5px;
    padding: 2px 7px; border: 1px solid var(--border-strong); border-radius: 4px;
    background: var(--bg); color: var(--fg); min-width: 44px; text-align: center;
  }
  /* Floating hint at bottom */
  #kb-hint {
    position: fixed; bottom: 24px; right: 24px; z-index: 90;
    background: var(--panel); border: 1px solid var(--border-strong);
    padding: 8px 14px; border-radius: 999px;
    font-family: var(--sans); font-size: 12px; color: var(--muted);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    opacity: 0; transform: translateY(8px);
    transition: opacity .4s, transform .4s;
  }
  #kb-hint.show { opacity: 1; transform: translateY(0); }
  #kb-hint .kb {
    font-family: var(--mono); font-size: 10.5px;
    padding: 1px 5px; border: 1px solid var(--border-strong); border-radius: 3px;
    background: var(--bg); color: var(--fg); margin: 0 4px;
  }
  .wrap { max-width: 1240px; margin: 0 auto; padding: 28px 36px 80px; }
  .test-eyebrow {
    font-size: 10.5px; letter-spacing: 0.20em; text-transform: uppercase;
    color: var(--muted); margin-bottom: 12px; font-family: var(--mono);
    display: flex; align-items: center; gap: 12px;
  }
  .badge {
    display: inline-flex; padding: 3px 9px; border-radius: 5px;
    font-size: 9.5px; letter-spacing: 0.16em; font-weight: 700;
    font-family: var(--mono);
  }
  .badge-official { background: rgba(94,234,212,0.12); color: var(--teal); border: 1px solid rgba(94,234,212,0.25); }
  .badge-generated { background: rgba(168,85,247,0.12); color: var(--purple); border: 1px solid rgba(168,85,247,0.28); }
  h1 {
    font-family: var(--sans); font-weight: 600; font-size: 26px;
    margin: 0 0 6px; letter-spacing: -0.014em; color: var(--fg);
  }
</style></head><body>
<header class="topbar">
  <div class="crumbs">
    <a href="/app" style="color:var(--muted)">Workspace</a><span class="sep">▸</span>
    <a href="/section/{{ test.section }}" style="color:var(--muted)">{{ section_label }}</a><span class="sep">▸</span>
    <b>Test {{ display_num }}</b>
  </div>
  <div class="top-actions">
    <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
    <a class="btn ghost" href="/section/{{ test.section }}">← Back to {{ section_label }}</a>
  </div>
</header>
<div class="wrap">
  {% if test.source == 'official' %}
    <div class="test-eyebrow">
      <span class="badge badge-official">OFFICIAL ACT</span>
      Form {{ test.form_code }} · {{ test.month }} {{ test.year }}
    </div>
    <h1>{{ section_label }}</h1>
  {% elif test.source == 'generated' %}
    <div class="test-eyebrow">
      <span class="badge badge-generated">AI-GENERATED</span>
      {{ test.form_code }} · Sonnet
    </div>
    <h1>{{ section_label }}</h1>
  {% else %}
    <div class="test-eyebrow">{{ section_label }} · Drill {{ display_num }}</div>
    <h1>{{ section_label }} practice {{ display_num }}</h1>
  {% endif %}
  <div class="test-meta">
    <span>{{ qcount }} questions</span>
    <span>~{{ minutes }} min recommended</span>
  </div>

  <div class="timer">
    <span>⏱ <span class="t" id="timer">00:00</span></span>
    <button onclick="resetTimer()">Reset</button>
  </div>

  <div class="results" id="results">
    <div class="eyebrow" style="margin:0 0 8px">Score</div>
    <div class="score" id="score">—</div>
    <div class="muted" id="score-meta" style="font-size:13px; margin-top:4px"></div>
    <div class="breakdown" id="breakdown"></div>
  </div>

  <div class="test-grid">
    <div class="passage-col">
      {# Text view is preferred whenever any text exists; image is a fallback. #}
      {% set has_text_view = (passage_text_marked or passage_text) %}
      {% if has_text_view and passage_div_html %}
        <div class="passage-mode-toggle">
          <button class="mode-btn on" data-mode="text" onclick="switchPassageMode('text')">Text</button>
          <button class="mode-btn" data-mode="image" onclick="switchPassageMode('image')">Original</button>
        </div>
      {% endif %}
      {% if passage_text_marked %}
        <div class="passage-text passage-mode" data-mode="text">{{ passage_text_marked|safe }}</div>
      {% elif passage_text %}
        <pre class="passage-text passage-mode" data-mode="text">{{ passage_text }}</pre>
      {% endif %}
      {% if passage_div_html %}
        <div class="passage-image passage-mode{% if has_text_view %} hidden{% endif %}" data-mode="image">{{ passage_div_html|safe }}</div>
      {% endif %}
      {% if not passage_text and not passage_div_html and test.section != 'math' %}
        <p class="passage-empty">No passage text stored for this test yet.</p>
      {% endif %}
      <style>
        .frag-warning {
          background: rgba(251,191,36,0.06); border: 1px solid rgba(251,191,36,0.22);
          border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;
          font-size: 12px; color: #fbbf24; line-height: 1.5;
        }
      </style>
    </div>
    <div class="questions-col">
      <div class="passage-wrap" id="passage">{{ passage_html|safe }}</div>
      <div class="controls">
        <button class="btn" id="submitBtn" onclick="grade()">Submit answers</button>
        <button class="btn ghost" onclick="resetTest()">Reset test</button>
      </div>
    </div>
  </div>

  <div class="nav-row">
    {% if prev_id %}<a href="/test/{{ prev_id }}" class="btn ghost">← Prev test</a>{% else %}<span></span>{% endif %}
    {% if next_id %}<a href="/test/{{ next_id }}" class="btn ghost">Next test →</a>{% else %}<span></span>{% endif %}
  </div>
</div>

<script>
  const ANSWERS = {{ answers_json|safe }};
  const QCOUNT = {{ qcount }};
  const GLOBAL_Q = {{ global_q_json|safe }};
  const SECTION = "{{ test.section }}";

  // Disarm the embedded CrackAB form — we grade client-side.
  document.querySelectorAll('#passage form').forEach(f => {
    f.addEventListener('submit', e => { e.preventDefault(); grade(); });
  });

  // Simple timer (counts up)
  let startedAt = Date.now(); let timerInt;
  function tick() {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    const mm = String(Math.floor(s/60)).padStart(2,'0');
    const ss = String(s%60).padStart(2,'0');
    document.getElementById('timer').textContent = `${mm}:${ss}`;
  }
  timerInt = setInterval(tick, 1000); tick();
  function resetTimer() { startedAt = Date.now(); tick(); }

  // ─── Keyboard shortcuts ─────────────────────────────────────────────
  // 1-5 / A-E / F-J → select answer for the focused (or first unanswered) question
  // J/↓ → next question · K/↑ → prev question · ⏎ → submit/grade · R → reset
  // ? → show shortcut overlay
  function shortcutQuestionEls() {
    return [...document.querySelectorAll('#passage > form, #passage > div, #passage > p')]
      .reduce((acc, el) => {
        // Group radios by their `name` attribute (one logical question per name)
        const radios = el.querySelectorAll ? el.querySelectorAll('input[type=radio]') : [];
        radios.forEach(r => {
          if (!acc._seen.has(r.name)) { acc._seen.add(r.name); acc.list.push(r.name); }
        });
        return acc;
      }, { _seen: new Set(), list: [] }).list;
  }
  function questionFocusIndex() {
    // find first question with no selection
    const names = shortcutQuestionEls();
    for (let i = 0; i < names.length; i++) {
      if (!document.querySelector(`input[name="${names[i]}"]:checked`)) return i;
    }
    return Math.max(0, names.length - 1);
  }
  let focusIdx = -1;  // -1 means "auto-pick first unanswered"
  function focusQuestion(idx) {
    const names = shortcutQuestionEls();
    if (!names.length) return;
    focusIdx = Math.max(0, Math.min(names.length - 1, idx));
    const radio = document.querySelector(`input[name="${names[focusIdx]}"]`);
    if (radio) {
      const row = radio.closest('.radio, label, p, div');
      if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // glow ring
      document.querySelectorAll('.kb-focus').forEach(el => el.classList.remove('kb-focus'));
      const q = row && row.closest('p, div');
      if (q) q.classList.add('kb-focus');
    }
  }
  function pickAnswer(letter) {
    const names = shortcutQuestionEls();
    if (!names.length) return;
    const idx = focusIdx < 0 ? questionFocusIndex() : focusIdx;
    const target = names[idx];
    const candidates = document.querySelectorAll(`input[name="${target}"]`);
    for (const r of candidates) {
      if ((r.value || '').toUpperCase() === letter) {
        r.checked = true;
        r.dispatchEvent(new Event('change', { bubbles: true }));
        // advance focus to next question after a brief beat
        setTimeout(() => focusQuestion(idx + 1), 80);
        return;
      }
    }
  }
  function letterFromKey(key) {
    const k = key.toUpperCase();
    if (k >= 'A' && k <= 'E') return k;
    if (k >= 'F' && k <= 'J') return k;
    if (k >= '1' && k <= '5') {
      // For even questions in English/Reading/Science (F-J), but easier: just try ABCDE first.
      // Map 1→A, 2→B, 3→C, 4→D, 5→E and if not present, try F-J equivalents.
      return 'ABCDE'[parseInt(k, 10) - 1];
    }
    return null;
  }
  document.addEventListener('keydown', function(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === 'j' || k === 'ArrowDown') {
      e.preventDefault();
      focusQuestion((focusIdx < 0 ? questionFocusIndex() : focusIdx) + 1);
    } else if (k === 'k' || k === 'ArrowUp') {
      e.preventDefault();
      focusQuestion((focusIdx < 0 ? questionFocusIndex() : focusIdx) - 1);
    } else if (k === 'Enter') {
      e.preventDefault(); grade();
    } else if (k.toLowerCase() === 'r' && !e.shiftKey) {
      e.preventDefault(); resetTest();
    } else if (k === '?') {
      e.preventDefault(); toggleShortcutHelp();
    } else {
      const letter = letterFromKey(k);
      if (letter) {
        e.preventDefault();
        // Try mapped letter; if absent for this question, try the F-J variant
        const names = shortcutQuestionEls();
        const idx = focusIdx < 0 ? questionFocusIndex() : focusIdx;
        const target = names[idx];
        const has = [...document.querySelectorAll(`input[name="${target}"]`)]
          .some(r => (r.value || '').toUpperCase() === letter);
        if (has) {
          pickAnswer(letter);
        } else if (letter >= 'A' && letter <= 'E') {
          // Try F-J variant for this question (1→F, 2→G, 3→H, 4→J, 5→K)
          pickAnswer('FGHJK'['ABCDE'.indexOf(letter)]);
        }
      }
    }
  });
  function toggleShortcutHelp() {
    let pad = document.getElementById('kb-help');
    if (pad) { pad.remove(); return; }
    pad = document.createElement('div');
    pad.id = 'kb-help';
    pad.innerHTML = `<div class="kb-help-card">
      <h3>Keyboard shortcuts</h3>
      <div class="kb-row"><span class="kb">A B C D</span> select answer</div>
      <div class="kb-row"><span class="kb">F G H J</span> select answer (even Q's)</div>
      <div class="kb-row"><span class="kb">1 2 3 4 5</span> by position</div>
      <div class="kb-row"><span class="kb">J / ↓</span> next question</div>
      <div class="kb-row"><span class="kb">K / ↑</span> previous question</div>
      <div class="kb-row"><span class="kb">⏎</span> submit / re-grade</div>
      <div class="kb-row"><span class="kb">R</span> reset test</div>
      <div class="kb-row"><span class="kb">?</span> close this</div>
    </div>`;
    document.body.appendChild(pad);
  }
  // Tiny "press ? for shortcuts" hint on first load
  setTimeout(() => {
    if (sessionStorage.getItem('act-kb-hint-seen')) return;
    const hint = document.createElement('div');
    hint.id = 'kb-hint';
    hint.innerHTML = 'press <span class="kb">?</span> for shortcuts';
    document.body.appendChild(hint);
    setTimeout(() => hint.classList.add('show'), 50);
    setTimeout(() => { hint.classList.remove('show'); setTimeout(() => hint.remove(), 400); }, 6000);
    sessionStorage.setItem('act-kb-hint-seen', '1');
  }, 1500);

  function grade() {
    const passage = document.getElementById('passage');
    // collect user answers per question
    const user = {};
    passage.querySelectorAll('input[type="radio"]:checked').forEach(r => {
      user[r.name] = r.value;
    });
    // mark every radio option visually
    passage.querySelectorAll('input[type="radio"]').forEach(r => {
      const qn = r.name; const opt = r.value;
      // find the option label (next text/nodes until next input)
      let label = r.parentElement;
      // also tag the input itself + label classes
      r.classList.remove('opt-correct','opt-wrong');
      // walk siblings to find the option text node and class-it
      let n = r.nextSibling; let target = null;
      while (n && !(n.nodeType === 1 && n.tagName === 'INPUT')) {
        if (n.nodeType === 1) { target = n; break; }
        if (n.nodeType === 3 && n.textContent.trim()) {
          // wrap text node in a span so we can style it
          const span = document.createElement('span');
          span.textContent = n.textContent;
          n.parentNode.replaceChild(span, n);
          target = span; break;
        }
        n = n.nextSibling;
      }
      const correct = ANSWERS[qn];
      if (target) {
        target.classList.remove('opt-correct','opt-wrong');
        if (opt === correct) target.classList.add('opt-correct');
        else if (user[qn] === opt) target.classList.add('opt-wrong');
      }
    });
    // tally — radio names use crackab's global q_nums (e.g. "1051") not 1-15.
    // GLOBAL_Q maps position 1..N to the actual radio name. Use it.
    let right = 0, wrong = 0, blank = 0, ungradeable = 0;
    const cells = [];
    for (let i = 1; i <= QCOUNT; i++) {
      const radioName = String(GLOBAL_Q[String(i)] || i);
      const u = user[radioName]; const c = ANSWERS[radioName];
      let cls = 'blank', body = '—';
      // No published answer key for this question (scraping gap) — don't score it.
      if (c === null || c === undefined || c === '' || c === '...') { ungradeable++; cls = 'blank'; body = '·'; }
      else if (!u) { blank++; }
      else if (u === c) { right++; cls = 'right'; body = c; }
      else { wrong++; cls = 'wrong'; body = `${u}→${c}`; }
      cells.push(`<div class="qcell ${cls}"><span class="num">Q${i}</span><span class="ans">${body}</span></div>`);
    }
    const graded = QCOUNT - ungradeable;
    document.getElementById('score').innerHTML = `${right}<em>/${graded}</em>`;
    document.getElementById('score-meta').textContent =
      `${right} correct · ${wrong} wrong · ${blank} blank` + (ungradeable ? ` · ${ungradeable} no key` : '') + ` · ${graded ? Math.round(100*right/graded) : 0}%`;
    document.getElementById('breakdown').innerHTML = cells.join('');
    document.getElementById('results').classList.add('show');
    document.getElementById('results').scrollIntoView({behavior: 'smooth', block: 'start'});
    document.getElementById('submitBtn').textContent = 'Re-grade';
    addExplanationToggles();
    // POST attempt to the tracking API (silent — fire and forget)
    try {
      const userByQnum = {};
      for (let i = 1; i <= QCOUNT; i++) {
        const rn = String(GLOBAL_Q[String(i)] || i);
        if (user[rn]) userByQnum[rn] = user[rn];
      }
      fetch('/api/attempt', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          test_id: {{ test.id }},
          answers: userByQnum,
          correct: ANSWERS,
          duration_seconds: Math.floor((Date.now() - startedAt) / 1000),
        }),
      }).catch(() => {});
    } catch (e) {}
  }

  function addExplanationToggles() {
    // Inject a <details> "Show explanation" toggle after each question's options.
    const passage = document.getElementById('passage');
    // Find each question's last radio input — the explanation goes after it.
    for (let q = 1; q <= QCOUNT; q++) {
      // skip if we already added one
      if (passage.querySelector(`details[data-q="${q}"]`)) continue;
      // Radios are named with crackab's global q_num (e.g. "1051") not 1-15.
      const radioName = String(GLOBAL_Q[String(q)] || q);
      const radios = passage.querySelectorAll(`input[name="${radioName}"]`);
      if (!radios.length) continue;
      const lastRadio = radios[radios.length - 1];
      // walk forward from the last radio to find the end-of-options point
      // (next <input> = next question, or end of form)
      let insertAfter = lastRadio;
      let n = lastRadio.nextSibling;
      while (n) {
        if (n.nodeType === 1 && n.tagName === 'INPUT' && n.type === 'radio') break;
        if (n.nodeType === 1) insertAfter = n;
        n = n.nextSibling;
      }
      const gq = GLOBAL_Q[String(q)];
      if (!gq) continue;
      const details = document.createElement('details');
      details.className = 'q-explain';
      details.dataset.q = q;
      details.innerHTML = `
        <summary>▸ Show explanation for Q${q}</summary>
        <div class="panel"><span class="loading">Loading…</span></div>`;
      details.addEventListener('toggle', () => {
        if (details.open && !details.dataset.loaded) {
          details.dataset.loaded = 'pending';
          // Try crackab's explanation page first (only works for crackab tests);
          // fall back to AI tutor (works for everything).
          const radioName = String(GLOBAL_Q[String(q)] || q);
          fetch(`/api/explanation/${SECTION}/${gq}`)
            .then(r => r.ok ? r.json() : Promise.reject(r.status))
            .then(d => {
              details.querySelector('.panel').innerHTML = d.html;
              details.dataset.loaded = 'true';
            })
            .catch(() => {
              fetch('/api/tutor', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({test_id: {{ test.id }}, q_num: parseInt(radioName)}),
              })
              .then(r => r.ok ? r.json() : Promise.reject(r.status))
              .then(d => {
                details.querySelector('.panel').innerHTML =
                  '<div style="color:var(--accent);font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">AI tutor</div>' +
                  String(d.explanation).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g, '<br>');
                details.dataset.loaded = 'true';
              })
              .catch(err => {
                details.querySelector('.panel').innerHTML =
                  '<span class="loading">No explanation available.</span>';
                details.dataset.loaded = 'error';
              });
            });
        }
      });
      insertAfter.parentNode.insertBefore(details, insertAfter.nextSibling);
    }
  }

  // Toggle between OCR'd text view and original image scan view.
  function switchPassageMode(mode) {
    document.querySelectorAll('.passage-mode-toggle .mode-btn').forEach(b => {
      b.classList.toggle('on', b.dataset.mode === mode);
    });
    document.querySelectorAll('.passage-mode').forEach(el => {
      el.classList.toggle('hidden', el.dataset.mode !== mode);
    });
  }

  function resetTest() {
    document.querySelectorAll('#passage input[type="radio"]').forEach(r => r.checked = false);
    document.querySelectorAll('#passage span.opt-correct, #passage span.opt-wrong').forEach(s => {
      s.classList.remove('opt-correct','opt-wrong');
    });
    // Remove explanation toggles
    document.querySelectorAll('#passage details.q-explain').forEach(d => d.remove());
    document.getElementById('results').classList.remove('show');
    document.getElementById('submitBtn').textContent = 'Submit answers';
    resetTimer();
  }
</script>
{{ palette|safe }}
</body></html>
"""

@app.route("/test/<int:test_id>")
def test_page(test_id):
    cur = db().cursor()
    cur.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
    test = cur.fetchone()
    if not test:
        abort(404)
    test = dict(test)
    cur.execute("SELECT q_num, correct_answer, options_json FROM questions WHERE test_id = ? ORDER BY q_num", (test_id,))
    qs = cur.fetchall()
    answers = {str(r["q_num"]): r["correct_answer"] for r in qs}
    qcount = len(qs)

    # Compute this test's sequential position within its section (1..N).
    # Use that as the displayed "Test N" everywhere instead of crackab's
    # arbitrary test_number.
    cur.execute("""
        SELECT COUNT(*) FROM tests
        WHERE section = ?
          AND (test_number IS NULL) <= (? IS NULL)
          AND (
            (test_number IS NOT NULL AND ? IS NOT NULL AND
             (test_number < ? OR (test_number = ? AND id <= ?)))
            OR (test_number IS NULL AND ? IS NULL AND id <= ?)
          )
    """, (test["section"], test["test_number"], test["test_number"],
          test["test_number"], test["test_number"], test["id"],
          test["test_number"], test["id"]))
    display_num = cur.fetchone()[0] or 1

    # Renumber the question labels in passage_html: crackab's <p><b>N.</b></p>
    # tags use arbitrary numbers (sometimes 1-15, sometimes 16-30, sometimes
    # 1051-1065). Replace them with sequential 1..qcount so they match the AI
    # markers in the passage (<sub>1</sub>, <sub>2</sub>, ...).
    passage_html_str = test["passage_html"] or ""
    # Renumber form labels to sequential 1..N so the question column always
    # reads 1, 2, 3, ... (matches the AI markers in the text view).
    if passage_html_str:
        import re as _re
        counter = [0]
        def _renumber(m):
            counter[0] += 1
            return f"<p><b>{counter[0]}.</b>{m.group(1)}</p>"
        passage_html_str = _re.sub(
            r"<p><b>\d+\.</b>(.*?)</p>",
            _renumber,
            passage_html_str,
        )
    if not passage_html_str and qcount:
        # Synthesize form HTML from the questions table (official/generated tests
        # don't have crackab-style passage_html).
        import html as _html
        parts = ['<form name="TEST" onsubmit="return false">',
                 '<div class="myquestion" id="myquestion">']
        for i, qrow in enumerate(qs, 1):
            opts = json.loads(qrow["options_json"] or "{}")
            prompt = opts.pop("_prompt", "") or ""
            opts.pop("_explanation", None)
            qn = qrow["q_num"]
            # Question header
            if prompt:
                parts.append(f'<p><b>{i}.</b> {_html.escape(prompt)}</p>')
            else:
                parts.append(f'<p><b>{i}.</b></p>')
            # Sort options A,B,C,D,E or F,G,H,J,K
            opt_keys = sorted([k for k in opts.keys() if len(k) == 1])
            for letter in opt_keys:
                _raw = str(opts[letter]).strip()
                # Some scraped questions have a valid answer letter but empty
                # option text — show a clear placeholder instead of a blank choice.
                otext = _html.escape(_raw) if _raw else "<span style='opacity:.55'>(choice text unavailable)</span>"
                parts.append(
                    f'<div class="radio"><label>'
                    f'<input name="{qn}" type="radio" value="{letter}"/>'
                    f'{letter}. {otext}</label></div>'
                )
        parts.append('</div></form>')
        passage_html_str = "".join(parts)
    section_label = SECTION_LABELS.get(test["section"], test["section"])
    minutes = {"english": 9, "math": 15, "reading": 9, "science": 9}.get(test["section"], 10)
    # prev/next within same section
    cur.execute("""SELECT id FROM tests WHERE section = ? AND
                   (test_number, id) < (?, ?) ORDER BY test_number DESC, id DESC LIMIT 1""",
                (test["section"], test["test_number"] or 0, test["id"]))
    prev = cur.fetchone()
    cur.execute("""SELECT id FROM tests WHERE section = ? AND
                   (test_number, id) > (?, ?) ORDER BY test_number ASC, id ASC LIMIT 1""",
                (test["section"], test["test_number"] or 0, test["id"]))
    nxt = cur.fetchone()
    # The "global" question number for crackab's explanation URLs IS the
    # q_num value we stored (crackab's radio inputs are named with their
    # global question ID). The JS keys the explanation lookup by the
    # POSITIONAL question number (1..N) shown to the user, so map that.
    global_q_map = {}
    for i, q_num in enumerate([r["q_num"] for r in qs], 1):
        global_q_map[i] = q_num
    return render_template_string(
        TEST_HTML,
        base_css=BASE_CSS,
        palette=PALETTE_HTML,
        test=test, qcount=qcount,
        display_num=display_num,
        passage_text=test["passage_text"] or "",
        passage_text_marked=expl_mod.sanitize_html(test["passage_text_marked"] or ""),
        passage_div_html=expl_mod.sanitize_html(test["passage_div_html"] or ""),
        passage_html=expl_mod.sanitize_html(passage_html_str) or "<p class='muted'>No questions stored.</p>",
        answers_json=json.dumps(answers).replace("</", "<\\/"),
        global_q_json=json.dumps(global_q_map).replace("</", "<\\/"),
        section_label=section_label, minutes=minutes,
        prev_id=prev["id"] if prev else None,
        next_id=nxt["id"] if nxt else None,
    )

# ─── Official Forms tab — full released ACT tests imported from PDFs ──
OFFICIAL_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Official ACT Forms — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .form-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px 22px; margin-bottom: 10px;
    transition: border-color .12s;
  }
  .form-card:hover { border-color: var(--border-strong); }
  .form-card-head {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 14px;
  }
  .form-card-head .when {
    font-family: var(--sans); font-size: 15px; font-weight: 600;
    color: var(--fg); letter-spacing: -0.008em;
  }
  .form-card-head .code {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.18em;
    text-transform: uppercase; color: var(--muted);
  }
  .sec-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
  @media (max-width: 640px) { .sec-row { grid-template-columns: 1fr 1fr; } }
  .sec-tile {
    display: flex; flex-direction: column; gap: 3px;
    padding: 11px 10px; background: var(--panel-2);
    border: 1px solid var(--border); border-radius: 6px;
    text-decoration: none; color: var(--fg); text-align: center;
    transition: border-color .12s, background .12s;
  }
  .sec-tile:hover {
    background: var(--panel-3);
    border-color: var(--accent-dim);
    text-decoration: none;
  }
  .sec-tile .name { font-family: var(--sans); font-size: 12.5px; font-weight: 500; color: var(--fg); }
  .sec-tile .qc { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  .sec-empty {
    padding: 11px 10px; border-radius: 6px;
    background: transparent;
    border: 1px dashed var(--border-strong);
    color: var(--dim); text-align: center;
    font-size: 10.5px; letter-spacing: 0.12em; text-transform: uppercase;
  }
</style></head><body>
<div class="app">
{{ sidebar|safe }}
<main class="main">
  <header class="topbar">
    <div class="crumbs"><a href="/app" style="color:var(--muted)">Workspace</a><span class="sep">▸</span><b>Official forms</b></div>
    <div class="top-actions">
      <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
    </div>
  </header>
  <div class="canvas">
    <h1>Official forms</h1>
    <p class="subtitle">{{ forms|length }} real ACT forms imported from PDFs. Pick a section to take it.</p>
    {% if not forms %}
      <div class="card" style="text-align:center;padding:50px 30px;color:var(--muted)">None imported yet.</div>
    {% endif %}
    {% for form in forms %}
      <div class="form-card">
        <div class="form-card-head">
          <div class="when">{{ form.month }} {{ form.year }}</div>
          <div class="code">Form {{ form.form_code }}</div>
        </div>
        <div class="sec-row">
          {% set sec_map = {} %}
          {% for sec in form.sections %}{% set _ = sec_map.update({sec.section: sec}) %}{% endfor %}
          {% for sec_key, sec_label in [('english','English'), ('math','Math'), ('reading','Reading'), ('science','Science')] %}
            {% if sec_map.get(sec_key) %}
              <a class="sec-tile" href="/test/{{ sec_map[sec_key].id }}">
                <span class="name">{{ sec_label }}</span>
                <span class="qc">{{ sec_map[sec_key].qcount }} q</span>
              </a>
            {% else %}
              <div class="sec-empty">{{ sec_label }}<br><span style="opacity:.5">—</span></div>
            {% endif %}
          {% endfor %}
        </div>
      </div>
    {% endfor %}
  </div>
</main>
</div>
{{ palette|safe }}
</body></html>
"""

@app.route("/official")
def official_list():
    cur = db().cursor()
    cur.execute("""
        SELECT id, section, form_code, year, month,
               (SELECT COUNT(*) FROM questions WHERE test_id = tests.id) AS qcount
        FROM tests
        WHERE source = 'official'
        ORDER BY year DESC, form_code,
                 CASE section WHEN 'english' THEN 1 WHEN 'math' THEN 2
                              WHEN 'reading' THEN 3 WHEN 'science' THEN 4 ELSE 5 END
    """)
    rows = [dict(r) for r in cur.fetchall()]
    # Group rows by form_code
    by_form = {}
    for r in rows:
        key = (r["form_code"], r["year"], r["month"])
        if key not in by_form:
            by_form[key] = {
                "form_code": r["form_code"],
                "year": r["year"],
                "month": r["month"],
                "sections": [],
            }
        by_form[key]["sections"].append({
            "id": r["id"],
            "section": r["section"] or "",
            "label": (r["section"] or "")[:3].upper(),
            "qcount": r["qcount"],
        })
    forms = sorted(by_form.values(), key=lambda f: (-(f["year"] or 0), f["form_code"] or ""))
    return render_template_string(OFFICIAL_HTML, base_css=BASE_CSS,
                                  sidebar=shell_sidebar("official", section_counts()),
                                  palette=PALETTE_HTML, forms=forms)

# ─── Explanation endpoint (lazy-fetched, cached in DB) ─────────────
@app.route("/api/explanation/<section>/<int:global_q>")
def api_explanation(section, global_q):
    if section not in SECTION_LABELS:
        abort(404)
    html, cached = expl_mod.get_explanation_cached(section, global_q)
    if not html:
        return jsonify({"error": "no explanation available"}), 404
    return jsonify({"html": html, "cached": cached, "global_q": global_q})

# ─── boot ──────────────────────────────────────────────────────────
features.register(app)
landing.register(app)
diagnostic.register(app)
drill.register(app)
from forma import billing
billing.register(app)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5574)
    args = ap.parse_args()
    print(f" * Forma — http://127.0.0.1:{args.port}/", flush=True)
    print(f" * DB: {DB_PATH}", flush=True)
    app.run(host="127.0.0.1", port=args.port, debug=os.environ.get("DEBUG") == "1")
