"""Extra routes: attempts logging, dashboard, review, adaptive, full-length
simulation, search, topics, bookmarks.

Imported by app.py via `import features; features.register(app)`.
"""
import json
import os
import random
import sqlite3
import time
from collections import defaultdict
from datetime import datetime

from flask import g, render_template_string, request, jsonify, abort, redirect, make_response

from forma.db import db
from forma.shell import SECTION_LABELS, PALETTE_HTML, shell_sidebar
from forma import billing

_CRUMB_TITLES = {
    "home": "Today", "official": "Official forms", "generated": "AI-generated",
    "dashboard": "Stats", "review": "Review", "adaptive": "Adaptive",
    "full": "Full tests", "search": "Search",
}


def topbar(active=None):
    """Open the app-shell with sidebar + topbar. Pair with shell_close()."""
    from app import section_counts  # late import — section_counts lives in app.py
    sidebar = shell_sidebar(active, section_counts())
    title = _CRUMB_TITLES.get(active or "home", "Forma")
    return f'''<div class="app">{sidebar}<main class="main">
<header class="topbar">
  <div class="crumbs"><a href="/app" style="color:var(--muted)">Workspace</a><span class="sep">▸</span><b>{title}</b></div>
  <div class="top-actions">
    <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
  </div>
</header>'''


def shell_close():
    return f'</main></div>{PALETTE_HTML}'


# ═══════════════════════════════════════════════════════════════════
# 1. ATTEMPT LOGGING API
# ═══════════════════════════════════════════════════════════════════
def api_attempt():
    """POST /api/attempt — called by the test page JS on submit."""
    data = request.get_json(silent=True) or {}
    test_id = data.get("test_id")
    answers = data.get("answers", {})        # { q_num: user_answer }
    duration = data.get("duration_seconds", 0)
    if not test_id or not answers:
        return jsonify({"error": "missing test_id or answers"}), 400
    conn = db()
    cur = conn.cursor()
    # Re-derive correct answers from the DB — never trust the client-supplied
    # "correct" dict (it was forgeable, and a stale client could log wrong scores).
    # Only count gradeable questions: null/empty/"..." correct answers are
    # scraping gaps and must not be scored as wrong.
    correct = {str(r["q_num"]): r["correct_answer"]
               for r in cur.execute(
                   "SELECT q_num, correct_answer FROM questions WHERE test_id = ?",
                   (test_id,))}
    gradeable = {qn: c for qn, c in correct.items() if c not in (None, "", "...")}
    score = 0
    total = len(gradeable)
    rows = []
    for qnum_str, cor in gradeable.items():
        u = answers.get(qnum_str)
        is_c = 1 if (u and u == cor) else 0
        if is_c: score += 1
        rows.append((qnum_str, u, cor, is_c))
    pct = (score * 100.0 / total) if total else 0.0
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute("""INSERT INTO attempts (test_id, started_at, finished_at,
                   duration_seconds, score, total, pct) VALUES (?,?,?,?,?,?,?)""",
                (test_id, now, now, duration, score, total, pct))
    aid = cur.lastrowid
    for qn, u, cor, is_c in rows:
        try:
            cur.execute("""INSERT INTO attempt_answers
                           (attempt_id, q_num, user_answer, correct_answer, is_correct)
                           VALUES (?,?,?,?,?)""",
                        (aid, qn, u, cor, is_c))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return jsonify({"attempt_id": aid, "score": score, "total": total, "pct": round(pct, 1)})


# ═══════════════════════════════════════════════════════════════════
# 2. DASHBOARD
# ═══════════════════════════════════════════════════════════════════
DASHBOARD_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Dashboard — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .stat-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap:14px; margin-top:28px; }
  .stat-card {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-radius: 14px; padding: 26px 22px;
    box-shadow: var(--shadow-soft);
    position: relative; overflow: hidden;
    transition: border-color .2s, transform .2s;
  }
  .stat-card::before {
    content: ""; position: absolute; top: 0; left: 18px; right: 18px; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent-glow) 50%, transparent);
    opacity: 0;  transition: opacity .25s;
  }
  .stat-card:hover { border-color: var(--accent-dim); transform: translateY(-2px); }
  .stat-card:hover::before { opacity: 1; }
  .stat-card .num {
    font-family: var(--serif); font-size: 52px; font-weight: 600;
    color: var(--fg); line-height: 0.95; letter-spacing: -0.034em;
    font-variation-settings: "opsz" 144;
  }
  .stat-card .label {
    font-size: 10px; color: var(--muted); letter-spacing: 0.22em;
    text-transform: uppercase; margin-top: 12px; font-family: var(--mono);
  }
  .score-pred {
    margin: 36px 0 0;
    background:
      radial-gradient(700px 200px at 50% 0%, rgba(94,234,212,0.10), transparent 60%),
      linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border-strong);
    border-radius: 18px; padding: 36px 36px;
    box-shadow: var(--shadow-deep);
    position: relative; overflow: hidden;
  }
  .score-pred::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent) 50%, transparent);
    opacity: 0.5;
  }
  .score-pred .pred-label {
    font-size: 10px; letter-spacing: 0.3em; text-transform: uppercase;
    color: var(--muted); font-family: var(--mono);
    display: flex; align-items: center; gap: 12px;
  }
  .score-pred .pred-label::before {
    content: ""; width: 22px; height: 1px; background: var(--accent);
  }
  .score-pred .pred-num {
    font-family: var(--display); font-size: 92px; font-weight: 700;
    color: var(--fg); line-height: 0.95; letter-spacing: -0.05em;
    margin: 14px 0 18px;
  }
  .score-pred .pred-num .of {
    color: var(--muted); font-weight: 500; font-size: 0.55em; margin-left: 4px; letter-spacing: -0.02em;
  }
  .score-pred .pred-breakdown { display:flex; gap:8px; flex-wrap:wrap; }
  .score-pred .pred-pill {
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border-strong);
    color: var(--muted); padding: 8px 14px; border-radius: 999px;
    font-size: 11px; font-family: var(--mono); letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .score-pred .pred-pill b { color: var(--accent); margin-left: 6px; font-weight: 700; }
  .score-pred .pred-meta {
    font-size: 11px; color: var(--dim); margin-top: 16px;
    font-style: italic; font-family: var(--serif);
  }
  .sec-grid { display:grid; grid-template-columns: repeat(4,1fr); gap:14px; margin:20px 0 36px; }
  @media (max-width:760px) { .sec-grid { grid-template-columns: 1fr 1fr; } }
  .sec-card {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-radius: 14px; padding: 22px;
    box-shadow: var(--shadow-soft);
    transition: border-color .2s, transform .2s;
  }
  .sec-card:hover { border-color: var(--accent-dim); transform: translateY(-2px); }
  .sec-card h3 {
    font-family: var(--serif); font-size: 19px; font-weight: 500;
    margin-bottom: 4px; letter-spacing: -0.018em;
  }
  .sec-card .acc {
    font-family: var(--serif); font-size: 36px; color: var(--fg);
    font-weight: 600; margin: 8px 0;
    letter-spacing: -0.03em; line-height: 1;
    font-variation-settings: "opsz" 144;
  }
  .sec-card .meta { font-size: 11px; color: var(--muted); letter-spacing: 0.06em; }
  .recent-row {
    display: grid; grid-template-columns: 100px 1fr 80px 100px 80px;
    gap: 14px; align-items: center;
    padding: 14px 18px; border-bottom: 1px solid var(--border);
    font-size: 13.5px;
    transition: background .15s, transform .15s;
  }
  .recent-row:hover { background: rgba(94,234,212,0.025); transform: translateX(3px); }
  .recent-row .pct { font-family: var(--mono); font-weight: 700; letter-spacing: 0.04em; }
  .recent-row .pct.good { color: var(--accent); }
  .recent-row .pct.mid  { color: #fbbf24; }
  .recent-row .pct.bad  { color: var(--bad); }
  .recent-row a { color: var(--fg); }
  .recent-list {
    border: 1px solid var(--border); border-radius: 14px; overflow: hidden;
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
  }
  .recent-list .recent-row:last-child { border-bottom: 0; }
  .empty { color: var(--muted); font-style: italic; padding: 50px 30px; text-align: center; }
</style></head><body>
{{ topbar|safe }}
<div class="wrap">
  <div class="dash-head">
    <div>
      <div class="eyebrow">Your progress</div>
      <h1>Dashboard</h1>
    </div>
    {% if total_attempts > 0 %}
      <button class="reset-btn" onclick="resetStats()">Reset stats</button>
    {% endif %}
  </div>
  <style>
    .dash-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
    .reset-btn {
      background: transparent; border: 1px solid rgba(248,113,113,0.30);
      color: var(--bad); padding: 9px 16px; border-radius: 6px;
      font-family: var(--mono); font-size: 11px; letter-spacing: 0.14em;
      text-transform: uppercase; font-weight: 600; cursor: pointer;
      transition: background .12s, border-color .12s;
    }
    .reset-btn:hover { background: rgba(248,113,113,0.10); border-color: var(--bad); }
  </style>
  <script>
    function resetStats() {
      if (!confirm('Wipe all attempt history? This cannot be undone.')) return;
      fetch('/api/reset-stats', {method: 'POST'})
        .then(r => r.json())
        .then(d => {
          alert('Deleted ' + d.deleted_attempts + ' attempts.');
          location.reload();
        })
        .catch(e => alert('Failed: ' + e));
    }
  </script>

  <div class="stat-grid">
    <div class="stat-card"><div class="num">{{ total_attempts }}</div><div class="label">Tests Taken</div></div>
    <div class="stat-card"><div class="num">{{ total_q }}</div><div class="label">Questions Answered</div></div>
    <div class="stat-card"><div class="num">{{ overall_pct }}%</div><div class="label">Overall Accuracy</div></div>
    <div class="stat-card"><div class="num">{{ streak }}</div><div class="label">Day Streak</div></div>
  </div>

  {% if predicted_composite %}
  <div class="score-pred">
    <div class="pred-label">PROJECTED ACT COMPOSITE</div>
    <div class="pred-num">{{ predicted_composite }}</div>
    <div class="pred-breakdown">
      {% for s in sections %}
        {% if s.predicted %}
        <span class="pred-pill">{{ s.label }}: <b>{{ s.predicted }}</b></span>
        {% endif %}
      {% endfor %}
    </div>
    <div class="pred-meta">Estimate based on your accuracy. Rough scaling, not official.</div>
  </div>
  {% endif %}

  {% if chart.has_data %}
  <h2>Accuracy · last 30 days</h2>
  <div class="chart-card">
    <svg viewBox="0 0 {{ chart.W }} {{ chart.H }}" preserveAspectRatio="none" class="acc-chart">
      <!-- gridlines -->
      {% for g in chart.gridlines %}
      <line x1="{{ chart.pad_l }}" x2="{{ chart.W - chart.pad_r }}"
            y1="{{ chart.pad_t + chart.inner_h - g * chart.inner_h / 100 }}"
            y2="{{ chart.pad_t + chart.inner_h - g * chart.inner_h / 100 }}"
            stroke="rgba(255,255,255,0.04)" stroke-width="1" />
      <text x="{{ chart.pad_l - 4 }}" y="{{ chart.pad_t + chart.inner_h - g * chart.inner_h / 100 + 3 }}"
            text-anchor="end" font-family="JetBrains Mono" font-size="8" fill="var(--dim)">{{ g }}</text>
      {% endfor %}
      <!-- x-axis baseline -->
      <line x1="{{ chart.pad_l }}" x2="{{ chart.W - chart.pad_r }}"
            y1="{{ chart.pad_t + chart.inner_h }}" y2="{{ chart.pad_t + chart.inner_h }}"
            stroke="rgba(255,255,255,0.08)" stroke-width="1" />
      <!-- per-section polylines + dots -->
      {% for c in chart.sections %}
      <polyline points="{{ c.points }}" fill="none" stroke="{{ c.color }}" stroke-width="1.8"
                stroke-linejoin="round" stroke-linecap="round" opacity="0.9" />
      {% for pt in c.points.split(' ') %}
        {% set xy = pt.split(',') %}
        <circle cx="{{ xy[0] }}" cy="{{ xy[1] }}" r="2.4" fill="{{ c.color }}" />
      {% endfor %}
      {% endfor %}
    </svg>
    <div class="chart-legend">
      {% for c in chart.sections %}
      <div class="legend-row">
        <span class="legend-dot" style="background:{{ c.color }}"></span>
        <span class="legend-label">{{ c.label }}</span>
        <span class="legend-meta">{{ c.n_attempts }} attempts · last {{ c.last_pct }}%</span>
      </div>
      {% endfor %}
    </div>
  </div>
  <style>
    .chart-card {
      background: linear-gradient(180deg, var(--panel) 0%, var(--bg) 100%);
      border: 1px solid var(--border);
      border-radius: 12px; padding: 22px;
      margin-bottom: 28px;
    }
    .acc-chart { width: 100%; height: 200px; display: block; }
    .chart-legend {
      display: flex; flex-wrap: wrap; gap: 18px;
      margin-top: 14px; padding-top: 14px;
      border-top: 1px solid var(--border);
    }
    .legend-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
    .legend-dot { width: 8px; height: 8px; border-radius: 50%; }
    .legend-label { font-weight: 500; color: var(--fg); }
    .legend-meta { color: var(--muted); font-family: var(--mono); font-size: 11px; }
  </style>
  {% endif %}

  <h2>Per section</h2>
  <div class="sec-grid">
    {% for s in sections %}
    <div class="sec-card">
      <h3>{{ s.label }}</h3>
      <div class="acc">{{ s.pct }}%</div>
      <div class="meta">{{ s.right }}/{{ s.total }} correct · {{ s.attempts }} tests</div>
      {% if s.trend %}
        <svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none">
          <polyline points="{{ s.trend }}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
        </svg>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  <style>
    .spark { width: 100%; height: 30px; margin-top: 10px; opacity: 0.85; }
  </style>

  <h2>Recent attempts</h2>
  {% if recent %}
    <div class="recent-list">
    {% for r in recent %}
      <div class="recent-row">
        <span class="muted" style="font-size:11px">{{ r.when }}</span>
        <a href="/test/{{ r.test_id }}">{{ r.title }}</a>
        <span class="muted">{{ r.section }}</span>
        <span class="pct {{ r.cls }}">{{ r.pct }}%</span>
        <span class="muted">{{ r.score }}/{{ r.total }}</span>
      </div>
    {% endfor %}
    </div>
  {% else %}
    <div class="empty">
      <div style="font-size:42px;margin-bottom:12px">📊</div>
      <div style="font-family:var(--serif);font-size:22px;color:var(--fg);margin-bottom:8px">No data yet</div>
      <div style="margin-bottom:18px">Take any test — score, weak topics, projected ACT, and trends all populate from there.</div>
      <a href="/app" style="background:var(--accent);color:#0b1220;padding:11px 22px;border-radius:7px;font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;text-decoration:none">Pick a test →</a>
    </div>
  {% endif %}

  {% if weak_areas %}
  <h2>Where you're struggling</h2>
  <div class="recent-list">
    {% for w in weak_areas %}
      <div class="recent-row" style="grid-template-columns: 1fr 80px 100px">
        <span>{{ w.label }}</span>
        <span class="pct bad">{{ w.pct }}%</span>
        <span class="muted">{{ w.count }} wrong</span>
      </div>
    {% endfor %}
  </div>
  {% endif %}
</div>
{{ shell_close|safe }}
</body></html>
"""

def dashboard():
    cur = db().cursor()
    cur.execute("SELECT COUNT(*) FROM attempts")
    total_attempts = cur.fetchone()[0]
    cur.execute("SELECT SUM(total), SUM(score) FROM attempts")
    row = cur.fetchone()
    total_q = row[0] or 0
    total_right = row[1] or 0
    overall_pct = round((total_right / total_q * 100) if total_q else 0, 1)
    # per-section
    cur.execute("""SELECT t.section,
                          COUNT(DISTINCT a.id) AS attempts,
                          SUM(a.total) AS total_q,
                          SUM(a.score) AS right_q
                   FROM attempts a JOIN tests t ON t.id = a.test_id
                   GROUP BY t.section""")
    sec_rows = {r["section"]: r for r in cur.fetchall()}
    sections = []
    for key, label in SECTION_LABELS.items():
        r = sec_rows.get(key)
        if r:
            tot = r["total_q"] or 0
            rt = r["right_q"] or 0
            sections.append({
                "label": label, "attempts": r["attempts"],
                "total": tot, "right": rt,
                "pct": round(rt / tot * 100 if tot else 0, 1),
            })
        else:
            sections.append({"label": label, "attempts": 0, "total": 0, "right": 0, "pct": 0})
    # recent attempts (last 15)
    cur.execute("""SELECT a.id, a.test_id, a.score, a.total, a.pct, a.started_at,
                          t.title, t.section
                   FROM attempts a LEFT JOIN tests t ON t.id = a.test_id
                   ORDER BY a.started_at DESC LIMIT 15""")
    recent = []
    for r in cur.fetchall():
        pct = round(r["pct"] or 0, 0)
        cls = "good" if pct >= 75 else ("mid" if pct >= 50 else "bad")
        try:
            dt = datetime.fromisoformat(r["started_at"])
            when = dt.strftime("%b %-d, %-I:%M %p")
        except Exception:
            when = r["started_at"][:16]
        recent.append({
            "test_id": r["test_id"], "title": r["title"] or "—",
            "section": r["section"] or "—", "score": int(r["score"] or 0),
            "total": int(r["total"] or 0), "pct": int(pct), "cls": cls, "when": when,
        })
    # weak areas: math topics where pct < 60% & >= 5 questions answered
    cur.execute("""SELECT q.topic AS label,
                          COUNT(*) AS count,
                          AVG(aa.is_correct) * 100 AS pct
                   FROM attempt_answers aa
                   JOIN attempts a ON a.id = aa.attempt_id
                   JOIN questions q ON q.test_id = a.test_id AND q.q_num = aa.q_num
                   WHERE q.topic IS NOT NULL
                   GROUP BY q.topic
                   HAVING count >= 5 AND pct < 60
                   ORDER BY pct ASC LIMIT 10""")
    weak_areas = [{"label": r["label"] or "Unknown",
                   "count": int(r["count"]),
                   "pct": round(r["pct"], 0)} for r in cur.fetchall()]
    # streak: count consecutive days back from today with at least 1 attempt
    cur.execute("SELECT DISTINCT date(started_at) FROM attempts ORDER BY 1 DESC")
    dates = [r[0] for r in cur.fetchall()]
    streak = 0
    if dates:
        today = datetime.utcnow().date().isoformat()
        cur_date = datetime.utcnow().date()
        date_set = set(dates)
        while cur_date.isoformat() in date_set:
            streak += 1
            cur_date = datetime.fromordinal(cur_date.toordinal() - 1)
    # Sparkline trend: last 10 attempts per section, as a polyline points string
    for s in sections:
        key = s["label"].lower()
        cur.execute("""SELECT a.pct FROM attempts a JOIN tests t ON t.id=a.test_id
                       WHERE t.section = ? ORDER BY a.started_at DESC LIMIT 10""", (key,))
        rows = list(reversed([r[0] or 0 for r in cur.fetchall()]))
        if len(rows) >= 2:
            n = len(rows)
            pts = []
            for i, v in enumerate(rows):
                x = round(i * 100 / (n - 1), 1)
                y = round(30 - (v * 28 / 100), 1)  # invert so higher = up
                pts.append(f"{x},{y}")
            s["trend"] = " ".join(pts)
        else:
            s["trend"] = ""
    # Score prediction (rough)
    pct_by_section = {s["label"].lower(): s["pct"] for s in sections if s["total"] > 0}
    composite, scaled = predict_score(pct_by_section)
    for s in sections:
        s["predicted"] = scaled.get(s["label"].lower())
    # Score history chart: per-section daily-averaged accuracy over last 30 days.
    # Returns dict of section → list of {date, pct, attempts} for client SVG.
    cur.execute("""SELECT t.section AS section, date(a.started_at) AS d,
                          AVG(a.pct) AS pct, COUNT(*) AS n
                   FROM attempts a JOIN tests t ON t.id = a.test_id
                   WHERE a.started_at >= datetime('now', '-30 days')
                   GROUP BY t.section, d
                   ORDER BY t.section, d""")
    history = defaultdict(list)
    for r in cur.fetchall():
        history[r["section"]].append({
            "d": r["d"], "pct": round(r["pct"] or 0, 1), "n": int(r["n"]),
        })
    # Build SVG polyline points per section + overall envelope
    chart_sections = []
    SEC_COLORS = {"english": "#5eead4", "math": "#a78bfa",
                  "reading": "#f59e0b", "science": "#f87171"}
    W, H = 640, 140  # logical viewBox
    PAD_L, PAD_R, PAD_T, PAD_B = 18, 12, 8, 18
    INNER_W = W - PAD_L - PAD_R
    INNER_H = H - PAD_T - PAD_B
    all_days = sorted({pt["d"] for pts in history.values() for pt in pts})
    if all_days:
        # X-axis: use day index across 30-day window
        from datetime import date as _date, timedelta as _td
        today = _date.today()
        start = today - _td(days=29)
        day_index = {(start + _td(days=i)).isoformat(): i for i in range(30)}
        for sec_key, label in SECTION_LABELS.items():
            pts = history.get(sec_key, [])
            if not pts:
                continue
            coords = []
            for p in pts:
                if p["d"] not in day_index:
                    continue
                x = round(PAD_L + (day_index[p["d"]] / 29) * INNER_W, 1)
                y = round(PAD_T + INNER_H - (p["pct"] / 100) * INNER_H, 1)
                coords.append(f"{x},{y}")
            if coords:
                chart_sections.append({
                    "key": sec_key, "label": label,
                    "color": SEC_COLORS[sec_key],
                    "points": " ".join(coords),
                    "n_attempts": sum(p["n"] for p in pts),
                    "last_pct": round(pts[-1]["pct"]),
                })
    chart = {
        "sections": chart_sections, "W": W, "H": H,
        "pad_l": PAD_L, "pad_r": PAD_R, "pad_t": PAD_T, "pad_b": PAD_B,
        "inner_w": INNER_W, "inner_h": INNER_H,
        "gridlines": [25, 50, 75],  # horizontal at these % values
        "has_data": bool(chart_sections),
    }
    from app import BASE_CSS
    return render_template_string(DASHBOARD_HTML, base_css=BASE_CSS, shell_close=shell_close(),
                                  topbar=topbar("dashboard"),
                                  total_attempts=total_attempts,
                                  total_q=total_q, overall_pct=overall_pct,
                                  streak=streak, sections=sections,
                                  recent=recent, weak_areas=weak_areas,
                                  predicted_composite=composite,
                                  chart=chart)


# ═══════════════════════════════════════════════════════════════════
# 3. WRONG-ANSWER REVIEW
# ═══════════════════════════════════════════════════════════════════
REVIEW_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Review — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .filters { display:flex; gap:8px; margin:22px 0; flex-wrap: wrap; }
  .filters a {
    padding: 9px 16px; border-radius: 999px;
    border: 1px solid var(--border-strong);
    font-size: 10px; letter-spacing: 0.20em; text-transform: uppercase;
    color: var(--muted); text-decoration: none; font-family: var(--mono); font-weight: 600;
    transition: color .15s, border-color .15s, background .15s;
  }
  .filters a:hover { color: var(--fg); border-color: var(--accent-dim); }
  .filters a.on {
    background: var(--accent); color: #061018;
    border-color: var(--accent); font-weight: 700;
  }
  .wrong-q {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-left: 3px solid var(--bad);
    border-radius: 14px; padding: 24px 28px; margin: 14px 0;
    box-shadow: var(--shadow-soft);
    transition: border-color .2s, transform .2s;
  }
  .wrong-q:hover { transform: translateX(2px); border-color: var(--border-strong); border-left-color: var(--bad); }
  .wrong-q .meta {
    font-size: 10px; color: var(--muted); letter-spacing: 0.22em;
    text-transform: uppercase; font-family: var(--mono);
  }
  .wrong-q .prompt {
    font-family: var(--serif); font-size: 19px; font-weight: 500;
    margin: 12px 0 18px; letter-spacing: -0.012em; line-height: 1.4;
  }
  .wrong-q .opts { display: flex; flex-direction: column; gap: 6px; }
  .wrong-q .opt {
    padding: 10px 14px; border-radius: 8px; font-size: 14px;
    border: 1px solid var(--border);
  }
  .wrong-q .opt.your    { background: rgba(248,113,113,0.06); border-color: rgba(248,113,113,0.28); color: var(--bad); }
  .wrong-q .opt.correct { background: rgba(94,234,212,0.06); border-color: rgba(94,234,212,0.28); color: var(--accent); font-weight: 600; }
  .wrong-q .opt b { font-family: var(--mono); margin-right: 6px; }
  .wrong-q a.retake {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 16px; color: var(--accent); font-size: 10px;
    letter-spacing: 0.22em; text-transform: uppercase; font-family: var(--mono); font-weight: 700;
  }
  .wrong-q a.retake:hover { color: var(--fg); }
</style></head><body>
{{ topbar|safe }}
<div class="wrap">
  <div class="eyebrow">Wrong-Answer Review</div>
  <h1>Drill what you missed</h1>
  <p class="muted">{{ count }} questions you've gotten wrong, most recent first.</p>

  <div class="filters">
    <a href="/review" class="{% if not section %}on{% endif %}">All</a>
    {% for s in sections_avail %}
    <a href="/review?section={{ s }}" class="{% if section == s %}on{% endif %}">{{ s|title }}</a>
    {% endfor %}
  </div>

  {% if not items %}
    <div class="empty" style="padding:60px;text-align:center;color:var(--muted)">
      Take some tests first — wrong answers show up here for re-drilling.
    </div>
  {% endif %}

  {% for w in items %}
    <div class="wrong-q">
      <div class="meta">{{ w.section|title }} · {{ w.title }} · Q{{ w.q_num }}</div>
      <div class="prompt">{{ w.prompt }}</div>
      <div class="opts">
        {% for letter, text in w.options %}
          <div class="opt {% if letter == w.user %}your{% endif %} {% if letter == w.correct %}correct{% endif %}">
            <b>{{ letter }}.</b> {{ text }}
          </div>
        {% endfor %}
      </div>
      <a class="retake" href="/test/{{ w.test_id }}">Retake this test →</a>
    </div>
  {% endfor %}
</div>
{{ shell_close|safe }}
</body></html>
"""

def review():
    section = request.args.get("section", "").strip().lower()
    cur = db().cursor()
    where = ["aa.is_correct = 0"]
    params = []
    if section in SECTION_LABELS:
        where.append("t.section = ?")
        params.append(section)
    sql = f"""SELECT aa.q_num, aa.user_answer AS user, aa.correct_answer AS correct,
                     q.options_json, t.id AS test_id, t.title, t.section,
                     a.started_at
              FROM attempt_answers aa
              JOIN attempts a ON a.id = aa.attempt_id
              JOIN questions q ON q.test_id = a.test_id AND q.q_num = aa.q_num
              JOIN tests t ON t.id = a.test_id
              WHERE {' AND '.join(where)}
              ORDER BY a.started_at DESC
              LIMIT 100"""
    cur.execute(sql, params)
    items = []
    for r in cur.fetchall():
        opts = json.loads(r["options_json"] or "{}")
        prompt = opts.pop("_prompt", "") or ""
        opts.pop("_explanation", None)
        opt_pairs = sorted([(k, v) for k, v in opts.items() if len(k) == 1])
        items.append({
            "q_num": r["q_num"], "user": r["user"], "correct": r["correct"],
            "prompt": prompt or "(no prompt stored)", "options": opt_pairs,
            "test_id": r["test_id"], "title": r["title"], "section": r["section"],
        })
    cur.execute("SELECT DISTINCT t.section FROM attempt_answers aa JOIN attempts a ON a.id=aa.attempt_id JOIN tests t ON t.id=a.test_id WHERE aa.is_correct=0")
    sections_avail = [r[0] for r in cur.fetchall() if r[0]]
    from app import BASE_CSS
    return render_template_string(REVIEW_HTML, base_css=BASE_CSS, shell_close=shell_close(),
                                  topbar=topbar("review"),
                                  count=len(items), items=items,
                                  section=section, sections_avail=sections_avail)


# ═══════════════════════════════════════════════════════════════════
# 4. ADAPTIVE PRACTICE
# ═══════════════════════════════════════════════════════════════════
ADAPTIVE_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Adaptive — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .strategy {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-radius: 16px; padding: 30px 32px; margin: 18px 0;
    box-shadow: var(--shadow-soft);
    position: relative; overflow: hidden;
    transition: border-color .2s, transform .2s;
  }
  .strategy::before {
    content: ""; position: absolute; top: 0; left: 30px; right: 30px; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent-glow) 50%, transparent);
    opacity: 0.5;
  }
  .strategy:hover { border-color: var(--accent-dim); transform: translateY(-2px); }
  .strategy h3 {
    font-family: var(--serif); font-weight: 500; font-size: 26px;
    margin-bottom: 10px; letter-spacing: -0.022em; line-height: 1.15;
  }
  .strategy h3 b { color: var(--accent); font-style: italic; font-weight: 600; }
  .strategy .why {
    color: var(--muted); font-size: 14.5px; line-height: 1.65;
    margin-bottom: 18px; font-family: var(--serif); max-width: 60ch;
  }
  .topic-list {
    margin-top: 14px;
    border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
  }
  .topic-row {
    padding: 13px 18px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; font-size: 13.5px;
    transition: background .15s;
  }
  .topic-row:last-child { border-bottom: 0; }
  .topic-row:hover { background: rgba(94,234,212,0.025); }
  .topic-row span:last-child { font-family: var(--mono); font-weight: 700; letter-spacing: 0.04em; }
</style></head><body>
{{ topbar|safe }}
<div class="wrap">
  <div class="eyebrow">Adaptive Practice</div>
  <h1>Drill what'll move your score</h1>
  <p class="muted">Picks practice that targets your weakest topics based on your history.</p>

  {% if not has_history %}
    <div class="strategy">
      <h3>No history yet</h3>
      <p class="why">The engine needs signal to adapt. Take the 60-second diagnostic — five real ACT math questions — and we'll seed your weak spots from there.</p>
      <a href="/diagnostic" class="btn">Start 60-sec diagnostic →</a>
      <a href="/section/english" class="btn" style="margin-left:8px;background:transparent;border:1px solid var(--border-strong);color:var(--fg-2)">Or browse tests</a>
    </div>
  {% else %}
    <div class="strategy">
      <h3>Weakest topic: {{ weakest_topic }}</h3>
      <p class="why">{{ weakest_pct }}% on {{ weakest_count }} questions. Recommended: drill 15 questions on this topic from the bank.</p>
      <a href="/adaptive/drill?topic={{ weakest_topic_key }}" class="btn">Drill 15 →</a>
    </div>
    <div class="strategy">
      <h3>Weakest section: {{ weakest_section|title }}</h3>
      <p class="why">{{ weakest_section_pct }}% across {{ weakest_section_count }} questions. Recommended: take a fresh {{ weakest_section }} test you haven't seen.</p>
      <a href="/section/{{ weakest_section }}" class="btn">Browse {{ weakest_section }} →</a>
    </div>
    <h2 style="font-family:var(--serif);font-weight:400;margin:30px 0 8px">Topic breakdown</h2>
    <div class="topic-list">
      {% for t in topics %}
      <div class="topic-row">
        <span>{{ t.label }}</span>
        <span class="{% if t.pct < 60 %}bad{% elif t.pct < 75 %}mid{% else %}good{% endif %}" style="color:{% if t.pct < 60 %}var(--bad){% elif t.pct < 75 %}#fbbf24{% else %}var(--accent){% endif %}">{{ t.pct }}% ({{ t.count }} q)</span>
      </div>
      {% endfor %}
    </div>
  {% endif %}
</div>
{{ shell_close|safe }}
</body></html>
"""

def adaptive():
    cur = db().cursor()
    # Topic stats
    cur.execute("""SELECT q.topic AS label, COUNT(*) AS count,
                          AVG(aa.is_correct) * 100 AS pct
                   FROM attempt_answers aa
                   JOIN attempts a ON a.id = aa.attempt_id
                   JOIN questions q ON q.test_id = a.test_id AND q.q_num = aa.q_num
                   WHERE q.topic IS NOT NULL
                   GROUP BY q.topic
                   HAVING count >= 3
                   ORDER BY pct ASC""")
    topics = [{"label": r["label"], "count": int(r["count"]),
               "pct": round(r["pct"], 0)} for r in cur.fetchall()]
    cur.execute("""SELECT t.section AS sec, COUNT(*) AS count,
                          AVG(aa.is_correct) * 100 AS pct
                   FROM attempt_answers aa
                   JOIN attempts a ON a.id = aa.attempt_id
                   JOIN tests t ON t.id = a.test_id
                   GROUP BY t.section
                   HAVING count >= 3
                   ORDER BY pct ASC""")
    sec_stats = [(r["sec"], int(r["count"]), round(r["pct"], 0)) for r in cur.fetchall()]
    has_history = bool(topics) or bool(sec_stats)
    ctx = {"has_history": has_history}
    if topics:
        w = topics[0]
        ctx["weakest_topic"] = w["label"]
        ctx["weakest_topic_key"] = w["label"]
        ctx["weakest_pct"] = w["pct"]
        ctx["weakest_count"] = w["count"]
    elif has_history:
        ctx["weakest_topic"] = "(no math topic data yet)"
        ctx["weakest_topic_key"] = ""
        ctx["weakest_pct"] = 0
        ctx["weakest_count"] = 0
    if sec_stats:
        s = sec_stats[0]
        ctx["weakest_section"] = s[0]
        ctx["weakest_section_count"] = s[1]
        ctx["weakest_section_pct"] = s[2]
    else:
        ctx["weakest_section"] = "english"
        ctx["weakest_section_count"] = 0
        ctx["weakest_section_pct"] = 0
    ctx["topics"] = topics
    from app import BASE_CSS
    return render_template_string(ADAPTIVE_HTML, base_css=BASE_CSS, shell_close=shell_close(),
                                  topbar=topbar("adaptive"), **ctx)


# ═══════════════════════════════════════════════════════════════════
# 5. FULL-LENGTH TIMED SIMULATION
# ═══════════════════════════════════════════════════════════════════
FULL_TEST_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Full Test — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .form-card {
    background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border);
    border-radius: 14px; padding: 26px 28px; margin: 12px 0;
    display: grid; grid-template-columns: 120px 1fr auto;
    gap: 24px; align-items: center;
    box-shadow: var(--shadow-soft);
    transition: border-color .2s, transform .2s;
  }
  .form-card:hover { border-color: var(--accent-dim); transform: translateY(-2px); }
  .form-card .code {
    font-family: var(--mono); font-size: 22px; font-weight: 600;
    color: var(--accent); letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .form-card .meta { color: var(--muted); font-size: 12px; letter-spacing: 0.04em; margin-top: 4px; }
  .form-card a.start {
    background: var(--accent); color: #061018;
    padding: 12px 22px; border-radius: 999px;
    font-family: var(--mono); font-weight: 700;
    font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
    text-decoration: none;
    display: inline-flex; align-items: center; gap: 8px;
    transition: transform .15s, box-shadow .2s;
  }
  .form-card a.start:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 26px rgba(94,234,212,0.30);
  }
  .timing {
    background: linear-gradient(180deg, rgba(94,234,212,0.05), transparent);
    border: 1px solid var(--border-strong);
    border-left: 2px solid var(--accent);
    padding: 18px 22px; margin: 22px 0; font-size: 13.5px; line-height: 1.7;
    border-radius: 0 12px 12px 0;
    font-family: var(--serif);
  }
  .timing b { color: var(--accent); font-weight: 600; }
</style></head><body>
{{ topbar|safe }}
<div class="wrap">
  <div class="eyebrow">Full-Length Simulation</div>
  <h1>Take a real-time ACT test</h1>
  <p class="muted">4 sections back to back, real ACT timing.</p>
  <div class="timing">
    <b>ACT timing:</b> English 45 min (75 q) · Math 60 min (60 q) · Reading 35 min (40 q) · Science 35 min (40 q)<br>
    <span class="muted">+ 10 min break between Math and Reading. Total: ~3 hours.</span>
  </div>
  {% if not forms %}
    <div style="margin-top:40px;padding:40px;text-align:center;background:var(--bg-2);border:1px solid rgba(255,255,255,0.05);border-radius:12px">
      <div style="font-size:42px;margin-bottom:12px">⏱</div>
      <div style="font-family:var(--serif);font-size:22px;color:var(--fg);margin-bottom:8px">No full tests imported yet</div>
      <div class="muted" style="margin-bottom:16px">Full tests come from official ACT PDFs or AI generation. They have all 4 sections.</div>
    </div>
  {% endif %}
  {% for f in forms %}
    <div class="form-card">
      <div class="code">{{ f.form_code }}</div>
      <div>
        <div style="font-family:var(--serif);font-size:17px">{{ f.month }} {{ f.year }}</div>
        <div class="meta">{{ f.source|title }} · {{ f.section_count }} sections · {{ f.q_total }} questions</div>
      </div>
      <a class="start" href="/full-test/{{ f.form_code }}">Start →</a>
    </div>
  {% endfor %}
</div>
{{ shell_close|safe }}
</body></html>
"""

def full_test_list():
    cur = db().cursor()
    cur.execute("""SELECT form_code, year, month, source,
                          COUNT(*) AS section_count,
                          SUM((SELECT COUNT(*) FROM questions WHERE test_id=tests.id)) AS q_total
                   FROM tests
                   WHERE source IN ('official','generated') AND form_code IS NOT NULL
                   GROUP BY form_code
                   ORDER BY year DESC, form_code""")
    forms = [dict(r) for r in cur.fetchall()]
    from app import BASE_CSS
    return render_template_string(FULL_TEST_HTML, base_css=BASE_CSS, shell_close=shell_close(),
                                  topbar=topbar("full"), forms=forms)


def full_test_run(form_code):
    """For a given form_code, redirect to its first section's test page —
    later iterations can chain sections with section-end → next-section flow."""
    cur = db().cursor()
    cur.execute("""SELECT id FROM tests WHERE form_code = ?
                   ORDER BY CASE section
                       WHEN 'english' THEN 1 WHEN 'math' THEN 2
                       WHEN 'reading' THEN 3 WHEN 'science' THEN 4 ELSE 5 END
                   LIMIT 1""", (form_code,))
    row = cur.fetchone()
    if not row:
        abort(404)
    return redirect(f"/test/{row['id']}")


# ═══════════════════════════════════════════════════════════════════
# 6. GENERATED forms list (alias of /official filtered)
# ═══════════════════════════════════════════════════════════════════
GENERATED_HTML = FULL_TEST_HTML  # reuse layout

def generated_list():
    cur = db().cursor()
    cur.execute("""SELECT form_code, year, month, source,
                          COUNT(*) AS section_count,
                          SUM((SELECT COUNT(*) FROM questions WHERE test_id=tests.id)) AS q_total
                   FROM tests
                   WHERE source = 'generated'
                   GROUP BY form_code
                   ORDER BY year DESC, form_code""")
    forms = [dict(r) for r in cur.fetchall()]
    from app import BASE_CSS
    return render_template_string(GENERATED_HTML, base_css=BASE_CSS, shell_close=shell_close(),
                                  topbar=topbar("generated"), forms=forms)


# ═══════════════════════════════════════════════════════════════════
# Register all routes with the existing app
# ═══════════════════════════════════════════════════════════════════
def predict_score(pct_by_section):
    """Rough composite-score predictor — ACT scaling is per-section raw→1-36.
    Approximate mapping (very rough): pct% → scaled score:
      90+ = 33  · 80-89 = 30  · 70-79 = 27  · 60-69 = 24  · 50-59 = 21
      40-49 = 18 · 30-39 = 15 · 20-29 = 12 · <20 = 9
    Composite = mean of 4 section scaled scores, rounded."""
    def pct_to_scaled(p):
        if p >= 90: return 33
        if p >= 80: return 30
        if p >= 70: return 27
        if p >= 60: return 24
        if p >= 50: return 21
        if p >= 40: return 18
        if p >= 30: return 15
        if p >= 20: return 12
        return 9
    scaled = {k: pct_to_scaled(v or 0) for k, v in pct_by_section.items()}
    # Composite = mean of sections the student has ACTUALLY practiced. pct_to_scaled(0)
    # is 9 (not 0), so averaging untouched sections would drag a real composite down
    # toward 9. Only average sections with real data.
    real = [pct_to_scaled(v) for v in pct_by_section.values() if v and v > 0]
    composite = round(sum(real) / len(real)) if real else None
    return composite, scaled


def api_tutor():
    """POST /api/tutor — explain a specific question with AI.
    Free users get 3 explanations/day; Premium is unlimited."""
    import os
    data = request.get_json(silent=True) or {}
    test_id = data.get("test_id")
    q_num = data.get("q_num")
    if not test_id or q_num is None:
        return jsonify({"error": "missing test_id or q_num"}), 400
    # Daily free limit (Premium = unlimited). new_cookie is set on the response
    # so anonymous free users get a stable per-day counter.
    allowed, remaining, new_cookie = billing.tutor_allowance()

    def finish(payload, status=200, count=False):
        if count:
            billing.record_tutor_use()
        resp = make_response(jsonify(payload), status)
        if new_cookie:
            resp.set_cookie("fv_id", new_cookie, max_age=60 * 60 * 24 * 365, samesite="Lax")
        return resp

    if not allowed:
        return finish({"error": "limit", "limit_reached": True,
                       "message": "You've used your 3 free AI explanations today. Upgrade to Premium for unlimited.",
                       "upgrade_url": "/upgrade"}, 402)
    cur = db().cursor()
    row = cur.execute(
        "SELECT options_json, correct_answer FROM questions WHERE test_id=? AND q_num=?",
        (test_id, q_num)
    ).fetchone()
    if not row:
        return jsonify({"error": "question not found"}), 404
    opts = json.loads(row["options_json"] or "{}")
    prompt_text = opts.pop("_prompt", "")
    explanation = opts.pop("_explanation", "")
    correct = row["correct_answer"]
    # If we already have an AI-generated explanation stored, return it
    if explanation:
        return finish({"explanation": explanation, "cached": True}, count=True)
    # Otherwise call OpenAI. Requires OPENAI_API_KEY in the environment (set it
    # in Railway). Degrade gracefully instead of 500-ing if it's not configured.
    if not os.environ.get("OPENAI_API_KEY"):
        return jsonify({"error": "AI tutor isn't configured right now."}), 503
    try:
        from openai import OpenAI
        oai = OpenAI()
        opt_str = "\n".join(f"{k}. {v}" for k, v in sorted(opts.items()) if len(k) == 1)
        user = f"Question: {prompt_text or '(no prompt)'}\n\nOptions:\n{opt_str}\n\nCorrect answer: {correct or '(unknown)'}\n\nIn 3-4 sentences, explain why the correct answer is right and why the most plausible wrong answer is wrong. Be specific."
        r = oai.chat.completions.create(
            model="gpt-4o-mini", max_tokens=400,
            messages=[
                {"role": "system", "content": "You are an ACT tutor. Be concise, specific, and direct. No fluff."},
                {"role": "user", "content": user},
            ],
        )
        out = r.choices[0].message.content.strip()
        return finish({"explanation": out, "cached": False}, count=True)
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


SEARCH_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Search — Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .search-box {
    display: flex; gap: 8px; margin: 22px 0 28px;
    position: relative;
  }
  .search-box input {
    flex: 1;
    background: linear-gradient(180deg, var(--bg-3), var(--bg-2));
    border: 1px solid var(--border-strong); color: var(--fg);
    padding: 16px 20px; border-radius: 12px;
    font-family: var(--serif); font-size: 16px; font-weight: 500;
    letter-spacing: -0.012em;
    transition: border-color .2s, box-shadow .2s;
  }
  .search-box input::placeholder { color: var(--dim); font-style: italic; }
  .search-box input:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-glow);
  }
  .search-box button {
    background: var(--accent); color: #061018;
    border: 0; padding: 0 26px; border-radius: 12px;
    font-family: var(--mono); font-weight: 700; font-size: 11px;
    letter-spacing: 0.20em; text-transform: uppercase; cursor: pointer;
    transition: transform .15s, box-shadow .2s;
  }
  .search-box button:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 26px rgba(94,234,212,0.30);
  }
  .hit {
    background: linear-gradient(180deg, var(--bg-3), var(--bg-2));
    border: 1px solid var(--border);
    border-radius: 14px; padding: 22px 26px; margin-bottom: 12px;
    box-shadow: var(--shadow-soft);
    transition: border-color .2s, transform .2s;
  }
  .hit:hover { border-color: var(--accent-dim); transform: translateX(3px); }
  .hit .meta {
    font-size: 10px; color: var(--muted); letter-spacing: 0.22em;
    text-transform: uppercase; margin-bottom: 10px; font-family: var(--mono);
  }
  .hit .snippet {
    font-family: var(--serif); font-size: 16px; line-height: 1.6;
    font-weight: 500; letter-spacing: -0.008em;
  }
  .hit .snippet mark {
    background: rgba(94,234,212,0.18); color: var(--accent);
    padding: 1px 4px; border-radius: 3px;
  }
  .hit a {
    display: inline-flex; align-items: center; gap: 6px;
    color: var(--accent); font-size: 10px;
    letter-spacing: 0.22em; text-transform: uppercase; font-family: var(--mono); font-weight: 700;
    margin-top: 12px;
  }
  .hit a:hover { color: var(--fg); }
</style></head><body>
{{ topbar|safe }}
<div class="wrap">
  <div class="eyebrow">Question Bank Search</div>
  <h1>Find any question</h1>
  <p class="muted">Search across {{ total_q }} questions in your library.</p>
  <form class="search-box" method="get">
    <input name="q" type="search" placeholder="Search question text, options, topics…" value="{{ q }}" autofocus>
    <button>Search</button>
  </form>
  <div class="search-filters">
    <a href="/search?q={{ q|urlencode }}" class="{% if not section %}on{% endif %}">All sections</a>
    {% for k, label in [('english', 'English'), ('math', 'Math'), ('reading', 'Reading'), ('science', 'Science')] %}
      <a href="/search?q={{ q|urlencode }}&section={{ k }}" class="{% if section == k %}on{% endif %}">{{ label }}</a>
    {% endfor %}
    {% if q %}
      <span class="ct">{{ hits|length }} result{% if hits|length != 1 %}s{% endif %}{% if hits|length == 60 %}+ (showing top 60){% endif %}</span>
    {% endif %}
  </div>
  <style>
    .search-filters {
      display: flex; gap: 6px; margin: 6px 0 22px; flex-wrap: wrap; align-items: center;
    }
    .search-filters a {
      padding: 6px 12px; border-radius: 999px;
      border: 1px solid var(--border-strong); color: var(--muted);
      font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase;
      font-weight: 600; font-family: var(--mono); text-decoration: none;
      transition: color .12s, border-color .12s, background .12s;
    }
    .search-filters a:hover { color: var(--fg); border-color: var(--accent-dim); }
    .search-filters a.on { background: var(--accent); border-color: var(--accent); color: #fff; }
    .search-filters .ct {
      margin-left: auto; font-size: 11px; color: var(--dim);
      font-family: var(--mono); letter-spacing: 0.06em;
    }
  </style>
  {% if q and not hits %}
    <p class="muted"><em>No matches for "{{ q }}".</em></p>
  {% endif %}
  {% for hit in hits %}
    <div class="hit">
      <div class="meta">{{ hit.section|title }} · {{ hit.title }} · Q{{ hit.q_num }}</div>
      <div class="snippet">{{ hit.snippet|safe }}</div>
      <a href="/test/{{ hit.test_id }}">Open test →</a>
    </div>
  {% endfor %}
</div>
{{ shell_close|safe }}
</body></html>
"""

def _fts_query(q):
    """Convert a casual user query into FTS5 MATCH syntax — escape special chars,
    quote multi-word phrases, support OR with explicit comma."""
    q = q.strip()
    # Strip FTS operators from user input to avoid syntax errors
    bad = ["'", '"', "(", ")", "*", "^", "/"]
    for b in bad:
        q = q.replace(b, " ")
    parts = [p for p in q.split() if p]
    if not parts:
        return None
    # Wrap each token in double quotes (treats as exact word, allows safe chars)
    return " ".join(f'"{p}"' for p in parts)


def search_view():
    from app import BASE_CSS
    raw_q = (request.args.get("q") or "").strip()
    section = (request.args.get("section") or "").strip().lower()
    cur = db().cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    total_q = cur.fetchone()[0]
    hits = []
    fts_available = True
    if raw_q and len(raw_q) >= 2:
        fts_q = _fts_query(raw_q)
        if fts_q:
            try:
                section_filter = ""
                params = [fts_q]
                if section in SECTION_LABELS:
                    section_filter = "AND f.section = ?"
                    params.append(section)
                # FTS5 ranking with snippet generation
                rows = cur.execute(f"""
                    SELECT f.test_id, f.q_num, f.section, t.title,
                           snippet(questions_fts, 3, '«mark»', '«/mark»', '…', 18) AS snip,
                           bm25(questions_fts) AS rank
                    FROM questions_fts f
                    JOIN tests t ON t.id = f.test_id
                    WHERE questions_fts MATCH ? {section_filter}
                    ORDER BY rank LIMIT 60
                """, params).fetchall()
                import html as _html
                for r in rows:
                    # HTML-escape the scraped body, then restore the <mark> tags
                    # from sentinels — prevents stored HTML in questions from
                    # injecting into the |safe-rendered snippet.
                    snip = _html.escape(r["snip"] or "").replace("«mark»", "<mark>").replace("«/mark»", "</mark>")
                    hits.append({
                        "test_id": r["test_id"], "title": r["title"] or "",
                        "section": r["section"], "q_num": r["q_num"], "snippet": snip,
                    })
            except sqlite3.OperationalError:
                fts_available = False
        # Fallback to LIKE if FTS is unavailable
        if not fts_available:
            rows = cur.execute("""
                SELECT t.id AS test_id, t.title, t.section, q.q_num, q.options_json
                FROM questions q JOIN tests t ON t.id = q.test_id
                WHERE q.options_json LIKE ?
                ORDER BY t.id DESC LIMIT 50
            """, ("%" + raw_q + "%",)).fetchall()
            for r in rows:
                opts = json.loads(r["options_json"] or "{}")
                body = (opts.get("_prompt") or "") + " " + " ".join(v for k, v in opts.items() if len(k) == 1)
                idx = body.lower().find(raw_q.lower())
                if idx < 0: continue
                start = max(0, idx - 50); end = min(len(body), idx + len(raw_q) + 100)
                import re as _re, html as _html
                snip = _html.escape(body[start:end])  # escape scraped body before marking
                esc_q = _html.escape(raw_q)
                snip = _re.sub(_re.escape(esc_q), lambda m: f"<mark>{m.group(0)}</mark>", snip, flags=_re.I)
                hits.append({"test_id": r["test_id"], "title": r["title"] or "",
                             "section": r["section"], "q_num": r["q_num"], "snippet": snip})
    return render_template_string(SEARCH_HTML, base_css=BASE_CSS, shell_close=shell_close(),
                                  topbar=topbar("search"), q=raw_q, hits=hits,
                                  total_q=total_q, section=section)


def api_reset_stats():
    """POST /api/reset-stats — wipe all attempts + attempt_answers. Admin-gated:
    this is globally destructive (one shared DB, no per-user data), so it requires
    the ADMIN_KEY env var and fails closed if it isn't configured."""
    admin_key = os.environ.get("ADMIN_KEY")
    supplied = (request.args.get("key")
                or request.headers.get("X-Admin-Key")
                or (request.get_json(silent=True) or {}).get("key"))
    if not admin_key or supplied != admin_key:
        return jsonify({"error": "unauthorized"}), 401
    conn = db()
    n = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    conn.execute("DELETE FROM attempt_answers")
    conn.execute("DELETE FROM attempts")
    conn.commit()
    return jsonify({"deleted_attempts": n})


TOPICS_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Topics · Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .filter-bar {
    display: flex; gap: 6px; margin: 16px 0 22px; flex-wrap: wrap;
  }
  .filter-bar a {
    padding: 7px 14px; border-radius: 999px;
    border: 1px solid var(--border-strong); color: var(--muted);
    font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
    font-weight: 600; font-family: var(--mono); text-decoration: none;
    transition: color .12s, border-color .12s, background .12s;
  }
  .filter-bar a:hover { color: var(--fg); border-color: var(--accent-dim); }
  .filter-bar a.on { background: var(--accent); border-color: var(--accent); color: #fff; }
  .filter-bar input {
    background: var(--panel); border: 1px solid var(--border-strong);
    color: var(--fg); padding: 7px 14px; border-radius: 999px;
    font-family: var(--sans); font-size: 12px; min-width: 200px;
    outline: none; transition: border-color .12s;
  }
  .filter-bar input:focus { border-color: var(--accent); }
  .sec-section h2 {
    font-size: 11px; font-family: var(--mono); font-weight: 600;
    color: var(--muted); letter-spacing: 0.22em; text-transform: uppercase;
    margin: 24px 0 10px; display: flex; align-items: center; gap: 14px;
  }
  .sec-section h2::after {
    content: ""; flex: 1; height: 1px; background: var(--border);
  }
  .sec-section h2 .ct { font-family: var(--mono); color: var(--dim); font-weight: 500; }
  .topic-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 6px; }
  .topic-tile {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border: 1px solid var(--border); border-radius: 7px;
    background: var(--panel); color: var(--fg);
    text-decoration: none; transition: border-color .12s, background .12s, transform .12s;
  }
  .topic-tile:hover {
    background: var(--panel-2); border-color: var(--accent-dim);
    transform: translateX(2px); text-decoration: none;
  }
  .topic-tile.dim { opacity: 0.55; }
  .topic-tile .name { font-size: 13.5px; font-weight: 500; line-height: 1.3; }
  .topic-tile .qct { font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .topic-tile .acc {
    font-family: var(--mono); font-size: 10.5px; font-weight: 600;
    padding: 2px 7px; border-radius: 4px; letter-spacing: 0.04em;
  }
  .topic-tile .acc.good { background: rgba(74,222,128,0.10); color: var(--green); }
  .topic-tile .acc.mid  { background: rgba(251,191,36,0.10); color: var(--amber); }
  .topic-tile .acc.bad  { background: rgba(248,113,113,0.10); color: var(--bad); }
  .topic-tile .acc.none { color: var(--dim); }
  .sec-pill {
    width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 8px;
  }
  .sec-pill.english { background: #5eead4; }
  .sec-pill.math    { background: #a78bfa; }
  .sec-pill.reading { background: #f59e0b; }
  .sec-pill.science { background: #f87171; }
</style></head><body>
<div class="app">
{{ sidebar|safe }}
<main class="main">
  <header class="topbar">
    <div class="crumbs"><a href="/app" style="color:var(--muted)">Workspace</a><span class="sep">▸</span><b>Topics</b></div>
    <div class="top-actions">
      <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
    </div>
  </header>
  <div class="canvas">
    <h1>Drill by topic</h1>
    <p class="subtitle">{{ total_topics }} topic banks · {{ total_q }} questions · weakest-first.</p>
    <div class="filter-bar">
      <a href="/topics" class="{% if not section %}on{% endif %}">All sections</a>
      <a href="/topics?section=english" class="{% if section == 'english' %}on{% endif %}">English</a>
      <a href="/topics?section=math"    class="{% if section == 'math' %}on{% endif %}">Math</a>
      <a href="/topics?section=reading" class="{% if section == 'reading' %}on{% endif %}">Reading</a>
      <a href="/topics?section=science" class="{% if section == 'science' %}on{% endif %}">Science</a>
      <input type="search" id="q" placeholder="Filter…" oninput="filterTopics()">
    </div>
    {% for sec_key, sec_label, sec_topics in groups %}
    {% if sec_topics %}
    <div class="sec-section">
      <h2><span class="sec-pill {{ sec_key }}"></span>{{ sec_label }} <span class="ct">{{ sec_topics|length }} topics · {{ sec_topics|sum(attribute='qcount') }} q</span></h2>
      <div class="topic-grid">
        {% for t in sec_topics %}
        <a class="topic-tile{% if t.attempted == 0 %} dim{% endif %}" data-key="{{ t.name|lower }} {{ t.section }} {{ t.slug }}" href="/test/{{ t.test_id }}">
          <span>
            <div class="name">{{ t.name }}</div>
            <div class="qct">{{ t.qcount }} q{% if t.attempted %} · {{ t.attempted }} attempted{% endif %}</div>
          </span>
          {% if t.attempted > 0 %}
            <span class="acc {% if t.pct >= 75 %}good{% elif t.pct >= 50 %}mid{% else %}bad{% endif %}">{{ t.pct }}%</span>
          {% else %}
            <span class="acc none">—</span>
          {% endif %}
        </a>
        {% endfor %}
      </div>
    </div>
    {% endif %}
    {% endfor %}
  </div>
</main>
</div>
<script>
function filterTopics() {
  const q = (document.getElementById('q').value || '').trim().toLowerCase();
  document.querySelectorAll('.topic-tile').forEach(el => {
    el.style.display = (!q || el.dataset.key.indexOf(q) >= 0) ? '' : 'none';
  });
  document.querySelectorAll('.sec-section').forEach(s => {
    const any = [...s.querySelectorAll('.topic-tile')].some(t => t.style.display !== 'none');
    s.style.display = any ? '' : 'none';
  });
}
</script>
{{ palette|safe }}
</body></html>
"""


def topics():
    """Index of all topic banks (Varsity Tutors), sorted weakest-first within each section."""
    section_filter = (request.args.get("section") or "").strip().lower()
    cur = db().cursor()
    # Per-topic accuracy from attempts
    cur.execute("""
      SELECT t.section AS section, t.topic AS slug, t.id AS test_id, t.title AS title,
             (SELECT COUNT(*) FROM questions WHERE test_id=t.id) AS qcount,
             (SELECT COUNT(*) FROM attempt_answers aa JOIN attempts a ON a.id=aa.attempt_id WHERE a.test_id=t.id) AS attempted,
             (SELECT AVG(aa.is_correct)*100 FROM attempt_answers aa JOIN attempts a ON a.id=aa.attempt_id WHERE a.test_id=t.id) AS pct
      FROM tests t
      WHERE t.source='varsity' AND t.topic IS NOT NULL
      ORDER BY t.section, t.topic
    """)
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["name"] = (d["slug"] or "").replace("-", " ").title()
        d["attempted"] = int(d["attempted"] or 0)
        d["pct"] = int(round(d["pct"] or 0))
        rows.append(d)
    # Group by section, sort weakest-first inside section
    groups_dict = defaultdict(list)
    for r in rows:
        groups_dict[r["section"]].append(r)
    for sec in groups_dict:
        groups_dict[sec].sort(key=lambda x: (x["attempted"] == 0, x["pct"], -x["qcount"]))
    order = ["english", "math", "reading", "science"]
    if section_filter in SECTION_LABELS:
        order = [section_filter]
    groups = [(k, SECTION_LABELS[k], groups_dict.get(k, [])) for k in order]
    from app import BASE_CSS, PALETTE_HTML, shell_sidebar, section_counts
    return render_template_string(TOPICS_HTML,
        base_css=BASE_CSS,
        sidebar=shell_sidebar("topics", section_counts()),
        palette=PALETTE_HTML,
        section=section_filter,
        groups=groups,
        total_topics=sum(len(v) for v in groups_dict.values()) if not section_filter
                     else len(groups_dict.get(section_filter, [])),
        total_q=sum(r["qcount"] for r in rows if not section_filter or r["section"] == section_filter),
    )


def api_bookmark():
    """POST /api/bookmark — toggle bookmark on a question.
    Body: {test_id, q_num, note?}. Returns {bookmarked: bool}."""
    data = request.get_json(silent=True) or {}
    test_id = data.get("test_id")
    q_num = data.get("q_num")
    if not test_id or q_num is None:
        return jsonify({"error": "missing test_id or q_num"}), 400
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM bookmarks WHERE test_id=? AND q_num=?", (test_id, q_num))
    exists = cur.fetchone() is not None
    if exists:
        cur.execute("DELETE FROM bookmarks WHERE test_id=? AND q_num=?", (test_id, q_num))
        conn.commit()
        return jsonify({"bookmarked": False})
    cur.execute("INSERT INTO bookmarks (test_id, q_num, note) VALUES (?, ?, ?)",
                (test_id, q_num, data.get("note") or None))
    conn.commit()
    return jsonify({"bookmarked": True})


def api_bookmarks_for_test():
    """GET /api/bookmarks?test_id=N → {q_nums: [..]}."""
    test_id = request.args.get("test_id")
    if not test_id:
        return jsonify({"error": "missing test_id"}), 400
    cur = db().cursor()
    cur.execute("SELECT q_num FROM bookmarks WHERE test_id=?", (test_id,))
    return jsonify({"q_nums": [r[0] for r in cur.fetchall()]})


BOOKMARKS_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<title>Bookmarks · Forma</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin><link rel="preconnect" href="https://cdn.fontshare.com" crossorigin><link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet"><link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{{ base_css|safe }}
  .bookmark-row {
    display: grid; grid-template-columns: auto 1fr auto auto;
    gap: 14px; align-items: center;
    padding: 14px 18px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--panel); margin-bottom: 6px;
    transition: border-color .12s, background .12s;
  }
  .bookmark-row:hover { background: var(--panel-2); border-color: var(--border-strong); }
  .bookmark-row .star { color: #fbbf24; font-size: 16px; }
  .bookmark-row .body { min-width: 0; }
  .bookmark-row .body .t { font-size: 13.5px; color: var(--fg); font-weight: 500; line-height: 1.35;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bookmark-row .body .meta { color: var(--muted); font-size: 11px; font-family: var(--mono); margin-top: 3px; }
  .bookmark-row .when { color: var(--dim); font-size: 11px; font-family: var(--mono); }
  .bookmark-row a.go {
    padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-strong);
    color: var(--muted); font-size: 10.5px; letter-spacing: 0.16em;
    text-transform: uppercase; font-family: var(--mono); font-weight: 600;
    text-decoration: none; transition: color .12s, border-color .12s;
  }
  .bookmark-row a.go:hover { color: var(--accent); border-color: var(--accent); }
  .bookmark-row .unstar {
    background: transparent; border: 0; color: var(--dim); cursor: pointer;
    font-size: 14px; padding: 6px 8px; transition: color .12s;
  }
  .bookmark-row .unstar:hover { color: var(--bad); }
</style></head><body>
<div class="app">
{{ sidebar|safe }}
<main class="main">
  <header class="topbar">
    <div class="crumbs"><a href="/app" style="color:var(--muted)">Workspace</a><span class="sep">▸</span><b>Bookmarks</b></div>
    <div class="top-actions">
      <button class="btn ghost" onclick="openPalette()"><span class="kbd">⌘K</span> Quick jump</button>
    </div>
  </header>
  <div class="canvas">
    <h1>Starred questions</h1>
    <p class="subtitle">{{ bookmarks|length }} question{% if bookmarks|length != 1 %}s{% endif %} you marked for later.</p>
    {% if not bookmarks %}
      <div class="card" style="text-align:center;padding:50px 30px;color:var(--muted)">
        Nothing starred yet. Hit the ☆ icon on any question to bookmark it.
      </div>
    {% endif %}
    {% for b in bookmarks %}
    <div class="bookmark-row" data-test="{{ b.test_id }}" data-q="{{ b.q_num }}">
      <span class="star">★</span>
      <div class="body">
        <div class="t">{{ b.snippet }}</div>
        <div class="meta">{{ b.section|title }} · {{ b.title }} · Q{{ b.q_num }}</div>
      </div>
      <span class="when">{{ b.when }}</span>
      <a class="go" href="/test/{{ b.test_id }}#q{{ b.q_num }}">Open →</a>
      <button class="unstar" onclick="unstar({{ b.test_id }}, {{ b.q_num }}, this)" title="Remove bookmark">✕</button>
    </div>
    {% endfor %}
  </div>
</main>
</div>
{{ palette|safe }}
<script>
function unstar(testId, qNum, btn) {
  fetch('/api/bookmark', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({test_id: testId, q_num: qNum})})
    .then(r => r.json()).then(_ => {
      const row = btn.closest('.bookmark-row');
      row.style.opacity = '0';
      setTimeout(() => row.remove(), 150);
    });
}
</script>
</body></html>
"""


def bookmarks_view():
    cur = db().cursor()
    cur.execute("""
      SELECT b.test_id, b.q_num, b.created_at, b.note,
             t.title, t.section, q.options_json
      FROM bookmarks b
      JOIN tests t ON t.id = b.test_id
      LEFT JOIN questions q ON q.test_id = b.test_id AND q.q_num = b.q_num
      ORDER BY b.created_at DESC
    """)
    bookmarks = []
    for r in cur.fetchall():
        d = dict(r)
        opts = {}
        try:
            opts = json.loads(d.get("options_json") or "{}")
        except Exception:
            pass
        prompt = (opts.get("_prompt") or "")
        # build snippet
        if prompt:
            snip = prompt[:140] + ("…" if len(prompt) > 140 else "")
        else:
            # NO CHANGE-style — fall back to choice texts
            choices = [v for k, v in opts.items() if len(k) == 1]
            snip = " · ".join(c[:30] for c in choices[:3]) or f"Q{d['q_num']}"
        # relative time
        from datetime import datetime as _dt
        try:
            dt = _dt.fromisoformat(d["created_at"])
            delta = (_dt.utcnow() - dt).total_seconds()
            if delta < 60: when = "just now"
            elif delta < 3600: when = f"{int(delta/60)}m ago"
            elif delta < 86400: when = f"{int(delta/3600)}h ago"
            elif delta < 86400*7: when = f"{int(delta/86400)}d ago"
            else: when = dt.strftime("%b %-d")
        except Exception:
            when = ""
        bookmarks.append({
            "test_id": d["test_id"], "q_num": d["q_num"],
            "title": (d["title"] or "—")[:50], "section": d["section"] or "—",
            "snippet": snip, "when": when,
        })
    from app import BASE_CSS, PALETTE_HTML, shell_sidebar, section_counts
    return render_template_string(BOOKMARKS_HTML,
        base_css=BASE_CSS,
        sidebar=shell_sidebar("bookmarks", section_counts()),
        palette=PALETTE_HTML,
        bookmarks=bookmarks,
    )


def register(app):
    app.add_url_rule("/api/attempt", "api_attempt", api_attempt, methods=["POST"])
    app.add_url_rule("/api/tutor", "api_tutor", api_tutor, methods=["POST"])
    app.add_url_rule("/api/reset-stats", "api_reset_stats", api_reset_stats, methods=["POST"])
    app.add_url_rule("/api/bookmark", "api_bookmark", api_bookmark, methods=["POST"])
    app.add_url_rule("/api/bookmarks", "api_bookmarks_for_test", api_bookmarks_for_test)
    app.add_url_rule("/dashboard", "dashboard", dashboard)
    app.add_url_rule("/review", "review", billing.premium_required("The review queue")(review))
    app.add_url_rule("/adaptive", "adaptive", billing.premium_required("The adaptive engine")(adaptive))
    app.add_url_rule("/full-test", "full_test_list", full_test_list)
    app.add_url_rule("/full-test/<form_code>", "full_test_run", full_test_run)
    app.add_url_rule("/generated", "generated_list", generated_list)
    app.add_url_rule("/search", "search_view", search_view)
    app.add_url_rule("/topics", "topics", topics)
    app.add_url_rule("/bookmarks", "bookmarks_view", bookmarks_view)
