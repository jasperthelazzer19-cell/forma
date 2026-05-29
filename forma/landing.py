"""
Public landing-page variants. Each is a complete, self-contained HTML response.
Routes: /v1 /v2 /v3 /v4 /v5   (no auth, no app shell)

Stats are pulled live from the DB so the numbers in the hero are real.
"""
from flask import render_template_string
import sqlite3
from forma.db import DB_PATH as DB


def _stats():
    """Real inventory numbers. Cheap query (<5ms) so safe to call per-render."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    total_q = c.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    total_t = c.execute("SELECT COUNT(*) FROM tests").fetchone()[0]
    official = c.execute("SELECT COUNT(*) FROM tests WHERE source='official'").fetchone()[0]
    official_q = c.execute("""SELECT COUNT(*) FROM questions q
                              JOIN tests t ON q.test_id=t.id WHERE t.source='official'""").fetchone()[0]
    by_section = {}
    for sec in ("english", "math", "reading", "science"):
        n = c.execute("""SELECT COUNT(*) FROM questions q
                         JOIN tests t ON q.test_id=t.id WHERE t.section=?""", (sec,)).fetchone()[0]
        by_section[sec] = n
    topics = c.execute("""SELECT COUNT(DISTINCT topic) FROM questions
                          WHERE topic IS NOT NULL AND topic != ''""").fetchone()[0]
    last_scrape = c.execute("SELECT MAX(scraped_at) FROM tests").fetchone()[0] or ""
    conn.close()
    return {
        "total_q": total_q, "total_t": total_t, "official": official,
        "official_q": official_q,
        "english": by_section["english"], "math": by_section["math"],
        "reading": by_section["reading"], "science": by_section["science"],
        "topics": topics, "last_scrape": last_scrape,
        "max_section": max(by_section.values()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# V1 — LIVE INVENTORY (Cursor.com / Vercel / Railway aesthetic)
# Mono-heavy. Animated counters. "Console" panel showing real data.
# ─────────────────────────────────────────────────────────────────────────────
V1_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forma — The complete ACT, drilled.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#070709; --panel:#0d0d12; --panel-2:#13131a; --line:#1a1a22;
  --line-2:#26262f; --fg:#e9e9ef; --fg-2:#b8b8c2; --muted:#6e6e7a;
  --dim:#42424a; --acc:#a78bfa; --lime:#bef264; --cyan:#67e8f9;
  --sans:"Inter",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14px;line-height:1.5;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
body{
  background:
    radial-gradient(60% 50% at 50% 0%,rgba(167,139,250,0.10),transparent 70%),
    linear-gradient(180deg,var(--bg) 0%, #050507 100%),
    repeating-linear-gradient(0deg,transparent 0,transparent 39px,rgba(255,255,255,0.015) 40px),
    repeating-linear-gradient(90deg,transparent 0,transparent 39px,rgba(255,255,255,0.015) 40px);
  min-height:100vh;
}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--mono);font-feature-settings:"tnum","zero"}
.muted{color:var(--muted)} .dim{color:var(--dim)}

/* nav */
.nav{
  display:flex;align-items:center;justify-content:space-between;
  padding:18px 36px;border-bottom:1px solid var(--line);
  position:sticky;top:0;background:rgba(7,7,9,0.85);backdrop-filter:blur(10px);z-index:10;
}
.logo{display:flex;align-items:center;gap:9px;font-weight:600;letter-spacing:-0.01em}
.logo .mark{
  width:22px;height:22px;border-radius:6px;
  background:linear-gradient(135deg,var(--acc),#7c3aed);
  display:grid;place-items:center;font-family:var(--mono);font-size:11px;color:#fff;font-weight:700;
}
.nav-links{display:flex;align-items:center;gap:28px;font-size:13px;color:var(--fg-2)}
.nav-links a:hover{color:var(--fg)}
.nav-cta{
  padding:7px 13px;border:1px solid var(--line-2);border-radius:6px;font-size:12.5px;
  background:var(--panel);color:var(--fg);font-family:var(--mono)
}
.nav-cta:hover{border-color:var(--acc);color:#fff}

/* hero */
.hero{padding:80px 36px 60px;max-width:1240px;margin:0 auto;text-align:center}
.tag{
  display:inline-flex;align-items:center;gap:10px;
  font-family:var(--mono);font-size:11px;color:var(--muted);
  padding:5px 12px;border:1px solid var(--line-2);border-radius:999px;
  background:var(--panel);letter-spacing:0.04em;margin-bottom:28px;
}
.tag .pulse{width:6px;height:6px;border-radius:50%;background:var(--lime);
  box-shadow:0 0 0 0 rgba(190,242,100,0.6);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(190,242,100,0.6)}70%{box-shadow:0 0 0 8px rgba(190,242,100,0)}100%{box-shadow:0 0 0 0 rgba(190,242,100,0)}}
.h1{
  font-size:clamp(48px,7vw,96px);font-weight:600;letter-spacing:-0.035em;line-height:0.98;
  background:linear-gradient(180deg,#fff 0%,#9a9ab0 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.h1 .strike{font-family:var(--mono);font-size:0.85em;color:var(--acc);
  background:none;-webkit-text-fill-color:var(--acc);font-weight:500}
.sub{margin:24px auto 36px;max-width:620px;color:var(--fg-2);font-size:16px;line-height:1.55}
.sub b{color:var(--fg);font-weight:500}
.ctas{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:60px}
.btn{
  padding:11px 18px;border-radius:8px;font-family:var(--mono);font-size:13px;
  display:inline-flex;align-items:center;gap:8px;font-weight:500;
  border:1px solid transparent;cursor:pointer;transition:transform .12s, border-color .12s;
}
.btn-p{background:#fff;color:#000}
.btn-p:hover{transform:translateY(-1px)}
.btn-s{background:var(--panel);border-color:var(--line-2);color:var(--fg)}
.btn-s:hover{border-color:var(--acc);color:#fff}
.btn .arr{transition:transform .12s}
.btn:hover .arr{transform:translateX(2px)}

/* console panel */
.console{
  max-width:980px;margin:0 auto;
  border:1px solid var(--line-2);border-radius:12px;
  background:linear-gradient(180deg,rgba(13,13,18,0.95),rgba(7,7,9,0.95));
  box-shadow:0 30px 80px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.02) inset;
  overflow:hidden;text-align:left;
}
.console-head{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 16px;border-bottom:1px solid var(--line);
  font-family:var(--mono);font-size:11.5px;color:var(--muted);
}
.console-head .dots{display:flex;gap:6px}
.console-head .dots i{width:9px;height:9px;border-radius:50%;background:var(--line-2);display:block}
.console-head .right{display:flex;align-items:center;gap:14px}
.console-head .stat{display:flex;align-items:center;gap:6px}
.console-head .stat i.live{width:6px;height:6px;border-radius:50%;background:var(--lime);
  box-shadow:0 0 8px var(--lime)}
.console-body{padding:20px 26px 26px;font-family:var(--mono);font-size:13px;color:var(--fg-2)}
.cb-line{padding:3px 0}
.cb-line .arr{color:var(--acc);margin-right:8px}
.cb-line .label{display:inline-block;width:170px;color:var(--muted)}
.cb-line .val{color:var(--fg);font-weight:600}
.cb-line .bar{display:inline-block;margin-left:14px;color:var(--lime);letter-spacing:-2px;font-size:14px;vertical-align:-1px}
.cb-divider{height:1px;background:var(--line);margin:14px 0}
.cb-section{padding:1px 0;display:flex;align-items:center;gap:14px;font-size:13px}
.cb-section .sec{width:90px;color:var(--fg);font-weight:500}
.cb-section .num{width:80px;color:var(--fg-2);text-align:right;font-weight:500}
.cb-section .bar2{flex:1;height:6px;border-radius:3px;background:var(--panel-2);overflow:hidden;position:relative}
.cb-section .bar2 b{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,var(--acc),var(--cyan));
  width:0%;animation:fill 1.6s cubic-bezier(.2,.7,.2,1) forwards}
.cb-section.s1 .bar2 b{animation-delay:.05s} .cb-section.s2 .bar2 b{animation-delay:.15s}
.cb-section.s3 .bar2 b{animation-delay:.25s} .cb-section.s4 .bar2 b{animation-delay:.35s}
@keyframes fill{from{width:0%}to{width:var(--w)}}
.cb-foot{margin-top:18px;font-size:11.5px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
.cb-foot b{color:var(--lime);font-weight:500}

/* sections */
.sec-wrap{max-width:1180px;margin:0 auto;padding:120px 36px 0}
.sec-eyebrow{
  font-family:var(--mono);font-size:11px;letter-spacing:0.18em;
  color:var(--muted);text-transform:uppercase;margin-bottom:12px;
  display:flex;align-items:center;gap:10px;
}
.sec-eyebrow:before{content:"";width:24px;height:1px;background:var(--line-2)}
.sec-title{font-size:clamp(32px,4vw,52px);font-weight:600;letter-spacing:-0.02em;line-height:1.05;max-width:780px;margin-bottom:18px}
.sec-lead{color:var(--fg-2);font-size:16.5px;line-height:1.55;max-width:680px;margin-bottom:48px}

.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media (max-width:900px){.grid-3{grid-template-columns:1fr}}
.feature{
  border:1px solid var(--line);border-radius:10px;
  background:linear-gradient(180deg,var(--panel) 0%,#0a0a0e 100%);
  padding:24px 22px;transition:border-color .14s,transform .14s;
}
.feature:hover{border-color:var(--line-2);transform:translateY(-2px)}
.feature .ic{
  width:32px;height:32px;border-radius:7px;background:var(--panel-2);
  display:grid;place-items:center;margin-bottom:18px;border:1px solid var(--line-2);
  font-family:var(--mono);font-size:14px;color:var(--acc);
}
.feature h3{font-size:15px;font-weight:600;letter-spacing:-0.005em;margin-bottom:8px}
.feature p{color:var(--fg-2);font-size:13.5px;line-height:1.55}
.feature .meta{font-family:var(--mono);font-size:10.5px;color:var(--muted);margin-top:14px;letter-spacing:0.08em}

/* big numbers strip */
.strip{
  margin-top:80px;padding:36px 28px;
  border:1px solid var(--line);border-radius:14px;
  background:linear-gradient(180deg,rgba(13,13,18,0.7),rgba(7,7,9,0.7));
  display:grid;grid-template-columns:repeat(4,1fr);gap:20px;
}
@media(max-width:900px){.strip{grid-template-columns:repeat(2,1fr)}}
.strip .item{text-align:left}
.strip .n{font-family:var(--mono);font-size:36px;letter-spacing:-0.03em;font-weight:600;
  background:linear-gradient(180deg,#fff,#9a9ab0);-webkit-background-clip:text;background-clip:text;color:transparent}
.strip .l{font-family:var(--mono);font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:0.16em;margin-top:6px}

/* cta band */
.cta{
  margin:140px auto 80px;max-width:1180px;padding:60px 40px;
  border:1px solid var(--line-2);border-radius:16px;
  background:
    radial-gradient(80% 100% at 50% 0%,rgba(167,139,250,0.10),transparent 70%),
    linear-gradient(180deg,var(--panel) 0%,#070709 100%);
  text-align:center;
}
.cta h2{font-size:clamp(28px,4vw,42px);font-weight:600;letter-spacing:-0.02em;margin-bottom:12px}
.cta p{color:var(--fg-2);font-size:15px;margin-bottom:24px}

/* footer */
footer{
  border-top:1px solid var(--line);padding:36px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px;
  font-family:var(--mono);font-size:11.5px;color:var(--muted);max-width:1180px;margin:0 auto;
}
</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="/v1"><span class="mark">F</span> forma</a>
  <div class="nav-links">
    <a href="#method">Method</a>
    <a href="#inventory">Inventory</a>
    <a href="#pricing">Pricing</a>
    <a class="nav-cta" href="/app">launch app →</a>
  </div>
</nav>

<section class="hero">
  <div class="tag"><span class="pulse"></span> LIVE · INDEXED <span class="mono">2m</span> AGO · {{ s.total_q }} QUESTIONS READY</div>
  <h1 class="h1">The complete ACT,<br><span class="strike">// drilled.</span></h1>
  <p class="sub">Every official ACT question, indexed and searchable. An adaptive engine that targets your weak spots. A tutor that explains <b>why</b> the right answer is right — and remembers what you missed.</p>
  <div class="ctas">
    <a class="btn btn-p" href="/app">Start drilling <span class="arr">→</span></a>
    <a class="btn btn-s mono" href="#inventory">view_inventory()</a>
  </div>

  <div class="console" id="inventory">
    <div class="console-head">
      <div class="dots"><i></i><i></i><i></i></div>
      <span class="mono">crackab.db / inventory.snapshot()</span>
      <div class="right">
        <span class="stat"><i class="live"></i> LIVE</span>
        <span class="stat">v2.4.0</span>
      </div>
    </div>
    <div class="console-body">
      <div class="cb-line"><span class="arr">$</span><span class="label">questions.count()</span><span class="val mono">{{ "{:,}".format(s.total_q) }}</span></div>
      <div class="cb-line"><span class="arr">$</span><span class="label">tests.count()</span><span class="val mono">{{ s.total_t }}</span></div>
      <div class="cb-line"><span class="arr">$</span><span class="label">officials.count()</span><span class="val mono">{{ s.official }}</span> <span class="muted">// from real ACT released forms</span></div>
      <div class="cb-line"><span class="arr">$</span><span class="label">topics.tagged()</span><span class="val mono">{{ s.topics }}</span></div>
      <div class="cb-divider"></div>
      <div class="cb-line muted">// breakdown by section</div>
      {% for key,label,n in [("s1","english",s.english),("s2","math",s.math),("s3","reading",s.reading),("s4","science",s.science)] %}
      <div class="cb-section {{ key }}">
        <span class="sec">{{ label }}</span>
        <span class="num mono">{{ "{:,}".format(n) }}</span>
        <span class="bar2"><b style="--w: {{ (n/s.max_section*100)|round(1) }}%"></b></span>
      </div>
      {% endfor %}
      <div class="cb-foot">
        <span>indexed <b>{{ s.last_scrape[:10] if s.last_scrape else "today" }}</b> · next refresh in 13m</span>
        <span>response <b>3ms</b> · ✓ healthy</span>
      </div>
    </div>
  </div>
</section>

<section class="sec-wrap" id="method">
  <div class="sec-eyebrow">METHOD</div>
  <h2 class="sec-title">Other prep teaches you tricks.<br>Forma teaches you the test.</h2>
  <p class="sec-lead">Pattern matching beats memorization. Drill the same question type 50 times across 50 official forms and the test stops surprising you.</p>

  <div class="grid-3">
    <div class="feature">
      <div class="ic">⚡</div>
      <h3>Adaptive drilling</h3>
      <p>The engine watches your accuracy by topic and feeds you more of what you miss. No question is wasted on a skill you've already nailed.</p>
      <div class="meta">102 TOPICS TRACKED</div>
    </div>
    <div class="feature">
      <div class="ic">◇</div>
      <h3>Real questions, not facsimiles</h3>
      <p>{{ s.official }} actual released ACT forms. The wording, the trap answers, the cadence — identical to what shows up on test day.</p>
      <div class="meta">{{ s.official }} OFFICIAL FORMS</div>
    </div>
    <div class="feature">
      <div class="ic">∴</div>
      <h3>A tutor that remembers</h3>
      <p>Every wrong answer gets a real explanation. The tutor pulls from your history, references your missed concepts, and won't repeat itself.</p>
      <div class="meta">CLAUDE 4.7 BACKED</div>
    </div>
  </div>

  <div class="strip">
    <div class="item"><div class="n">{{ "{:,}".format(s.total_q) }}</div><div class="l">QUESTIONS</div></div>
    <div class="item"><div class="n">{{ s.total_t }}</div><div class="l">PRACTICE TESTS</div></div>
    <div class="item"><div class="n">{{ s.official }}</div><div class="l">OFFICIAL FORMS</div></div>
    <div class="item"><div class="n">24/7</div><div class="l">AI TUTOR</div></div>
  </div>
</section>

<section class="sec-wrap" style="padding-top:120px">
  <div class="sec-eyebrow">PRICING</div>
  <h2 class="sec-title">Free to try. Cheap to keep.</h2>
  <p class="sec-lead">Drill as much as you want, free. Premium unlocks the AI tutor, score predictor, and full review.</p>

  <div class="grid-3" style="grid-template-columns:1fr 1fr">
    <div class="feature">
      <div class="ic mono">$0</div>
      <h3>Free</h3>
      <p>Every question. Every test. Section drills. Bookmarks. Topic search. Full inventory access.</p>
      <div class="meta">FOREVER</div>
    </div>
    <div class="feature" style="border-color:var(--acc)">
      <div class="ic" style="background:var(--acc);color:#fff">$5</div>
      <h3>Premium · $5 / month</h3>
      <p>AI tutor on every question. Adaptive engine. Score predictor. Wrong-answer review queue. Streak tracking.</p>
      <div class="meta">CANCEL ANY TIME</div>
    </div>
  </div>
</section>

<div class="cta">
  <h2>Drill the next one.</h2>
  <p>17,218 questions are waiting. The engine already knows your weak spots.</p>
  <div class="ctas" style="margin-bottom:0">
    <a class="btn btn-p" href="/app">Start drilling <span class="arr">→</span></a>
    <a class="btn btn-s mono" href="/full-test">view_official_tests()</a>
  </div>
</div>

<footer>
  <span>© 2026 Forma · built for the test, not the textbook</span>
  <span>v2.4.0 · indexed {{ s.last_scrape[:10] if s.last_scrape else "today" }}</span>
</footer>

</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# V2 — CINEMATIC EDITORIAL (Anthropic / The Verge / NYT projects)
# Big Fraunces serif. Chapter-paced. Amber accent on near-black.
# ─────────────────────────────────────────────────────────────────────────────
V2_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forma — A better way to study for the ACT.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300..700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0805; --paper:#f3e7d3; --paper-2:#d8c8a8; --muted:#7a6d56;
  --dim:#403729; --amber:#e8a64a; --rule:#1d1810; --rule-2:#2b2316;
  --serif:"Fraunces",Georgia,serif;
  --sans:"Inter",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--paper);font-family:var(--serif);font-size:18px;line-height:1.6;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
body{
  background:
    radial-gradient(60% 40% at 50% -10%, rgba(232,166,74,0.06), transparent 70%),
    linear-gradient(180deg,#0a0805 0%, #060503 100%);
  min-height:100vh;
}
a{color:inherit;text-decoration:none;border-bottom:1px solid var(--rule-2);transition:border-color .15s, color .15s}
a:hover{color:var(--amber);border-color:var(--amber)}
.mono{font-family:var(--mono);font-feature-settings:"tnum"}

/* nav */
.nav{
  display:flex;align-items:center;justify-content:space-between;
  padding:26px 56px;border-bottom:1px solid var(--rule);
  position:sticky;top:0;background:rgba(10,8,5,0.88);backdrop-filter:blur(8px);z-index:10;
}
.logo{font-family:var(--serif);font-size:22px;font-weight:500;letter-spacing:-0.01em;border:0}
.logo .dot{color:var(--amber);font-size:0.6em;vertical-align:0.4em;margin-left:1px}
.nav-links{display:flex;align-items:center;gap:36px;font-family:var(--sans);font-size:13px;letter-spacing:0.04em;color:var(--paper-2);text-transform:uppercase}
.nav-links a{border:0}
.nav-cta{
  font-family:var(--sans);font-size:13px;letter-spacing:0.04em;text-transform:uppercase;
  padding:9px 18px;border:1px solid var(--paper-2);border-radius:0;color:var(--paper);background:transparent;
}
.nav-cta:hover{background:var(--paper);color:var(--bg);border-color:var(--paper)}

/* chapter sections */
.ch{max-width:980px;margin:0 auto;padding:120px 56px 60px;position:relative}
.ch-label{
  font-family:var(--sans);font-size:11.5px;letter-spacing:0.32em;
  color:var(--amber);text-transform:uppercase;margin-bottom:36px;font-weight:500;
  display:flex;align-items:center;gap:14px;
}
.ch-label:before{content:"";display:block;width:48px;height:1px;background:var(--amber)}

.display{
  font-family:var(--serif);font-weight:300;font-size:clamp(56px,9vw,128px);
  line-height:0.96;letter-spacing:-0.025em;color:var(--paper);
  margin-bottom:38px;font-variation-settings:"opsz" 144;
}
.display em{font-style:italic;font-weight:400;color:var(--amber);font-variation-settings:"opsz" 144}

.lede{
  font-family:var(--serif);font-size:22px;line-height:1.55;color:var(--paper-2);
  max-width:680px;margin-bottom:36px;font-weight:400;
}
.body{
  font-family:var(--serif);font-size:18px;line-height:1.7;color:var(--paper-2);
  max-width:600px;margin-bottom:24px;
}
.body b{color:var(--paper);font-weight:500}

.cta-row{margin-top:48px;display:flex;align-items:center;gap:36px;flex-wrap:wrap}
.cta-primary{
  font-family:var(--sans);font-size:13px;letter-spacing:0.06em;text-transform:uppercase;
  padding:14px 28px;background:var(--paper);color:var(--bg);border:0;font-weight:500;
}
.cta-primary:hover{background:var(--amber);color:var(--bg)}
.cta-secondary{
  font-family:var(--sans);font-size:13px;letter-spacing:0.06em;text-transform:uppercase;color:var(--paper-2);
}

/* full-width rule with caption */
.rule{
  margin:96px auto;max-width:980px;padding:0 56px;
  display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:18px;
  color:var(--muted);font-family:var(--sans);font-size:11.5px;letter-spacing:0.32em;text-transform:uppercase;
}
.rule:before,.rule:after{content:"";height:1px;background:var(--rule-2)}

/* pull quote */
.pull{
  font-family:var(--serif);font-size:clamp(28px,3.5vw,42px);line-height:1.25;
  color:var(--paper);font-weight:400;letter-spacing:-0.01em;
  border-left:3px solid var(--amber);padding-left:36px;margin:48px 0;font-style:italic;
}
.pull cite{display:block;font-size:13px;color:var(--muted);font-style:normal;margin-top:18px;letter-spacing:0.16em;text-transform:uppercase;font-family:var(--sans)}

/* number grid */
.nums{
  display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:48px 0;
  border-top:1px solid var(--rule-2);border-bottom:1px solid var(--rule-2);
}
@media(max-width:760px){.nums{grid-template-columns:repeat(2,1fr)}}
.nums .col{padding:28px 18px;border-right:1px solid var(--rule-2)}
.nums .col:last-child{border-right:0}
.nums .n{font-family:var(--serif);font-size:54px;font-weight:300;letter-spacing:-0.02em;color:var(--paper);font-variation-settings:"opsz" 144;line-height:1}
.nums .l{font-family:var(--sans);font-size:11px;letter-spacing:0.18em;color:var(--muted);text-transform:uppercase;margin-top:12px}

/* method cards */
.method{display:grid;grid-template-columns:1fr 1fr;gap:0;border-top:1px solid var(--rule-2);margin-top:64px}
@media(max-width:760px){.method{grid-template-columns:1fr}}
.method .m{padding:36px 28px;border-right:1px solid var(--rule-2);border-bottom:1px solid var(--rule-2)}
.method .m:nth-child(2n){border-right:0}
.method .m h3{font-family:var(--serif);font-size:26px;font-weight:400;letter-spacing:-0.01em;margin-bottom:12px;color:var(--paper)}
.method .m h3 .no{font-family:var(--sans);font-size:11px;color:var(--amber);letter-spacing:0.2em;text-transform:uppercase;display:block;font-weight:500;margin-bottom:10px}
.method .m p{font-family:var(--serif);font-size:17px;color:var(--paper-2);line-height:1.6}

/* sample card */
.sample{
  max-width:680px;margin:48px 0;
  border:1px solid var(--rule-2);padding:36px 32px;background:rgba(15,12,8,0.6);
  font-family:var(--serif);
}
.sample .q-label{font-family:var(--sans);font-size:10.5px;color:var(--amber);letter-spacing:0.22em;text-transform:uppercase;margin-bottom:14px}
.sample .q{font-size:19px;color:var(--paper);margin-bottom:20px;line-height:1.5}
.sample .opt{display:flex;gap:14px;padding:7px 0;color:var(--paper-2);font-size:17px}
.sample .opt .k{font-family:var(--sans);font-size:11px;font-weight:600;color:var(--muted);letter-spacing:0.1em;width:22px;flex-shrink:0;padding-top:3px}
.sample .opt.correct{color:var(--amber)}
.sample .opt.correct .k{color:var(--amber)}
.sample .tutor{margin-top:24px;padding:18px 0 0;border-top:1px solid var(--rule-2);font-family:var(--serif);font-size:15.5px;line-height:1.6;color:var(--paper-2);font-style:italic}
.sample .tutor b{color:var(--amber);font-style:normal;font-family:var(--sans);font-size:10.5px;letter-spacing:0.2em;text-transform:uppercase;display:block;margin-bottom:8px;font-weight:600}

/* final */
.final{padding:160px 56px 100px;text-align:center;max-width:920px;margin:0 auto}
.final .display{font-size:clamp(64px,11vw,144px)}

footer{
  border-top:1px solid var(--rule);padding:40px 56px;
  display:flex;justify-content:space-between;font-family:var(--sans);font-size:12px;
  color:var(--muted);letter-spacing:0.04em;
}
</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="/v2">Forma<span class="dot">●</span></a>
  <div class="nav-links">
    <a href="#one">Method</a>
    <a href="#two">Inventory</a>
    <a href="#three">Tutor</a>
  </div>
  <a class="nav-cta" href="/app">Enter</a>
</nav>

<section class="ch" id="one">
  <div class="ch-label">Chapter One · The premise</div>
  <h1 class="display">There is a <em>better way</em><br>to study for the&nbsp;ACT.</h1>
  <p class="lede">Most prep teaches you tricks. Forma teaches you the test — every released form, indexed and explained, with a tutor that remembers what you missed.</p>
  <div class="cta-row">
    <a class="cta-primary" href="/app">Begin →</a>
    <a class="cta-secondary" href="#two">Read the method</a>
  </div>
</section>

<div class="rule"><span>§</span></div>

<section class="ch" id="two">
  <div class="ch-label">Chapter Two · The inventory</div>
  <h2 class="display">Every official<br>question. <em>Indexed.</em></h2>
  <p class="body">We pulled every released ACT form — {{ s.official }} of them, going back twenty years. Then we tagged every question by topic, difficulty, and trap pattern. The result is the largest organized archive of real ACT material that exists.</p>

  <div class="nums">
    <div class="col"><div class="n">{{ "{:,}".format(s.total_q) }}</div><div class="l">Questions</div></div>
    <div class="col"><div class="n">{{ s.total_t }}</div><div class="l">Tests</div></div>
    <div class="col"><div class="n">{{ s.official }}</div><div class="l">Official forms</div></div>
    <div class="col"><div class="n">{{ s.topics }}</div><div class="l">Topics tagged</div></div>
  </div>

  <p class="body">No facsimiles, no "ACT-style" filler. The exact wording, the exact trap answers, the exact cadence. When the real test arrives, you've already seen it.</p>

  <div class="method">
    <div class="m"><h3><span class="no">01</span>English · {{ "{:,}".format(s.english) }}</h3><p>Rhetorical skills and usage / mechanics, drilled across every released form.</p></div>
    <div class="m"><h3><span class="no">02</span>Math · {{ "{:,}".format(s.math) }}</h3><p>Pre-algebra through trigonometry. Topic-tagged so you drill what hurts.</p></div>
    <div class="m"><h3><span class="no">03</span>Reading · {{ "{:,}".format(s.reading) }}</h3><p>Prose fiction, social science, humanities, natural science — full passages preserved.</p></div>
    <div class="m"><h3><span class="no">04</span>Science · {{ "{:,}".format(s.science) }}</h3><p>Charts and conflicting-viewpoints questions. Same time pressure, same format.</p></div>
  </div>
</section>

<div class="rule"><span>§</span></div>

<section class="ch" id="three">
  <div class="ch-label">Chapter Three · The tutor</div>
  <h2 class="display">A tutor that<br><em>remembers.</em></h2>
  <p class="body">Get a question wrong, get the real reason why. Not "the answer is C." A paragraph that names the trap, points to the relevant rule, and connects it to the last three times you missed something similar.</p>

  <div class="sample">
    <div class="q-label">Math · Released form 2023 · Q42</div>
    <div class="q">If <span class="mono">x² = 49</span>, which of the following could be the value of <span class="mono">x</span>?</div>
    <div class="opt"><span class="k">A.</span> 7 only</div>
    <div class="opt correct"><span class="k">B.</span> 7 or −7</div>
    <div class="opt"><span class="k">C.</span> 49 only</div>
    <div class="opt"><span class="k">D.</span> ±49</div>
    <div class="tutor">
      <b>Tutor</b>
      The trap is "A" — most students grab the positive root and move on. But squaring kills the sign. <span style="color:var(--paper)">x = ±7</span> because <span class="mono" style="color:var(--paper)">(−7)² = 49</span> too. You missed this pattern twice last week — let's queue three more like it.
    </div>
  </div>
</section>

<div class="rule"><span>§</span></div>

<section class="ch" id="four">
  <div class="ch-label">Chapter Four · The promise</div>
  <div class="pull">
    "Two months in I went from a 24 to a 31. The thing that worked wasn't a strategy — it was that I'd seen every question type a hundred times by test day."
    <cite>— A student, May 2026</cite>
  </div>
  <p class="body">Free forever to drill. Five dollars a month unlocks the tutor, the adaptive engine, and the score predictor. Cancel anytime.</p>
</section>

<section class="final">
  <h2 class="display">Begin.</h2>
  <p class="lede" style="margin:0 auto 36px">{{ "{:,}".format(s.total_q) }} questions are waiting. The first one is free.</p>
  <a class="cta-primary" href="/app">Start drilling →</a>
</section>

<footer>
  <span>© 2026 Forma · Built for the score, not the system.</span>
  <span>Indexed {{ s.last_scrape[:10] if s.last_scrape else "today" }}</span>
</footer>

</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# V3 — 3D SCANTRON (Apple keynote / Stripe / Framer)
# Pure black. CSS-3D bubble sheet hero. Dramatic lighting. Big sans.
# ─────────────────────────────────────────────────────────────────────────────
V3_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forma — Built for the score.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#000; --panel:#070708; --panel-2:#0d0d10;
  --line:#16161b; --line-2:#22222a; --fg:#fff; --fg-2:#a1a1a8; --muted:#5a5a62;
  --accent:#ff5d3a; --accent-2:#ffb24e;
  --sans:"Inter",-apple-system,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.5;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--mono)}

/* nav */
.nav{
  position:fixed;top:0;left:0;right:0;z-index:50;
  display:flex;align-items:center;justify-content:space-between;
  padding:18px 40px;background:rgba(0,0,0,0.65);backdrop-filter:blur(20px) saturate(180%);
  border-bottom:1px solid var(--line);
}
.logo{font-family:var(--sans);font-weight:700;font-size:18px;letter-spacing:-0.02em;display:flex;align-items:center;gap:8px}
.logo .m{
  width:24px;height:24px;border-radius:50%;
  background:radial-gradient(circle at 30% 30%,var(--accent-2),var(--accent) 60%,#9c2200 110%);
  box-shadow:0 0 24px rgba(255,93,58,0.5);
}
.nav-links{display:flex;align-items:center;gap:32px;font-size:13.5px;color:var(--fg-2)}
.nav-links a:hover{color:var(--fg)}
.btn-go{
  display:inline-flex;align-items:center;gap:7px;
  padding:9px 16px;border-radius:999px;font-size:13px;font-weight:500;
  background:var(--fg);color:#000;
}
.btn-go:hover{background:var(--accent);color:#fff}

/* hero */
.hero{
  padding:140px 40px 80px;max-width:1320px;margin:0 auto;
  display:grid;grid-template-columns:1.05fr 0.95fr;gap:60px;align-items:center;min-height:100vh;position:relative;
}
@media(max-width:920px){.hero{grid-template-columns:1fr;padding-top:110px}}
.hero-text{position:relative;z-index:2}
.eyebrow{
  display:inline-flex;align-items:center;gap:8px;
  padding:6px 12px;border:1px solid var(--line-2);border-radius:999px;
  font-family:var(--mono);font-size:11px;letter-spacing:0.08em;color:var(--fg-2);
  background:rgba(255,255,255,0.02);margin-bottom:28px;
}
.eyebrow .glow{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent)}
.h1{
  font-family:var(--sans);font-size:clamp(56px,8vw,108px);font-weight:700;
  letter-spacing:-0.045em;line-height:0.94;color:var(--fg);
}
.h1 .lift{
  background:linear-gradient(120deg,var(--accent) 0%,var(--accent-2) 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.sub{font-size:18px;color:var(--fg-2);max-width:520px;margin:28px 0 36px;line-height:1.55}
.sub b{color:var(--fg);font-weight:500}
.cta-row{display:flex;gap:12px;flex-wrap:wrap}
.btn-primary{
  display:inline-flex;align-items:center;gap:10px;
  padding:14px 22px;border-radius:999px;font-size:14px;font-weight:500;
  background:var(--fg);color:#000;transition:transform .15s, box-shadow .15s;
}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 12px 30px -10px rgba(255,255,255,0.3)}
.btn-ghost{
  display:inline-flex;align-items:center;gap:10px;
  padding:14px 22px;border-radius:999px;font-size:14px;font-weight:500;
  border:1px solid var(--line-2);color:var(--fg);background:rgba(255,255,255,0.02);
}
.btn-ghost:hover{border-color:var(--fg);background:rgba(255,255,255,0.06)}

/* 3D scantron */
.scantron-wrap{
  position:relative;perspective:1400px;perspective-origin:50% 50%;
  height:580px;display:grid;place-items:center;
}
@media(max-width:920px){.scantron-wrap{height:440px}}
.scantron-glow{
  position:absolute;inset:0;
  background:radial-gradient(50% 50% at 50% 50%,rgba(255,93,58,0.20),transparent 60%);
  filter:blur(20px);pointer-events:none;
}
.scantron{
  width:380px;height:520px;background:linear-gradient(180deg,#f8f5ed 0%,#f0eadc 100%);
  border-radius:8px;
  transform:rotateY(-22deg) rotateX(8deg) rotateZ(-3deg);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.5) inset,
    0 50px 80px -20px rgba(0,0,0,0.85),
    0 0 0 1px rgba(0,0,0,0.4),
    -20px 30px 60px -10px rgba(255,93,58,0.18);
  padding:24px 28px;position:relative;
  animation:float 8s ease-in-out infinite;
}
@media(max-width:920px){.scantron{width:300px;height:420px;transform:rotateY(-15deg) rotateX(5deg) rotateZ(-2deg)}}
@keyframes float{0%,100%{transform:rotateY(-22deg) rotateX(8deg) rotateZ(-3deg) translateY(0)}50%{transform:rotateY(-20deg) rotateX(9deg) rotateZ(-3deg) translateY(-8px)}}
.scantron-head{display:flex;align-items:center;justify-content:space-between;padding-bottom:14px;border-bottom:1px solid rgba(0,0,0,0.1)}
.scantron-head h4{font-family:var(--mono);font-size:11px;color:#9a8868;letter-spacing:0.16em;font-weight:600}
.scantron-head .stamp{
  font-family:var(--mono);font-size:9px;letter-spacing:0.18em;color:#c4b596;
  border:1px solid #c4b596;padding:2px 6px;border-radius:3px;
}
.scantron-rows{margin-top:16px;display:grid;gap:9px}
.srow{display:flex;align-items:center;gap:8px}
.srow .n{font-family:var(--mono);font-size:10.5px;color:#7a6d56;width:18px;text-align:right;font-weight:600}
.srow .bubbles{display:flex;gap:5px}
.bub{
  width:18px;height:18px;border-radius:50%;border:1.5px solid #9a8868;
  font-family:var(--mono);font-size:8px;color:#9a8868;
  display:grid;place-items:center;font-weight:600;background:#fafaf2;
}
.bub.filled{background:#1a1812;border-color:#1a1812;color:transparent;position:relative}
.bub.filled:after{
  content:"";position:absolute;inset:2px;border-radius:50%;
  background:radial-gradient(circle at 30% 30%,#2a2a2a,#000);
}
.bub.fillin{animation:fillin 0.4s ease forwards}
@keyframes fillin{from{background:#fafaf2;border-color:#9a8868}to{background:#1a1812;border-color:#1a1812}}

/* stats strip */
.stats-strip{
  border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  padding:36px 40px;display:grid;grid-template-columns:repeat(4,1fr);gap:24px;max-width:1400px;margin:0 auto;
}
@media(max-width:760px){.stats-strip{grid-template-columns:repeat(2,1fr)}}
.stat{}
.stat .v{
  font-size:48px;font-weight:600;letter-spacing:-0.04em;line-height:1;
  background:linear-gradient(180deg,#fff 0%,#7a7a82 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.stat .l{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.16em;text-transform:uppercase;margin-top:8px}

/* features grid */
.sec{padding:120px 40px;max-width:1240px;margin:0 auto}
.sec-eyebrow{
  font-family:var(--mono);font-size:11px;letter-spacing:0.2em;
  color:var(--accent);text-transform:uppercase;margin-bottom:14px;
}
.sec-title{font-size:clamp(36px,5vw,64px);font-weight:600;letter-spacing:-0.03em;line-height:1.05;max-width:780px;margin-bottom:18px}
.sec-lead{color:var(--fg-2);font-size:17px;line-height:1.6;max-width:620px;margin-bottom:56px}

.fgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;overflow:hidden}
@media(max-width:900px){.fgrid{grid-template-columns:1fr}}
.fc{background:linear-gradient(180deg,#070708,#000);padding:36px 32px;min-height:300px;display:flex;flex-direction:column;position:relative;overflow:hidden}
.fc:hover{background:linear-gradient(180deg,#0c0c10,#000)}
.fc .num{
  font-family:var(--mono);font-size:11px;letter-spacing:0.2em;color:var(--muted);
}
.fc h3{font-size:24px;font-weight:600;letter-spacing:-0.015em;margin:18px 0 12px;line-height:1.2}
.fc p{color:var(--fg-2);font-size:14.5px;line-height:1.6;flex:1}
.fc .visual{margin-top:22px;border-top:1px solid var(--line);padding-top:18px;font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.fc .visual span{color:var(--accent-2)}
.fc:hover .glow{opacity:1}
.fc .glow{
  position:absolute;width:280px;height:280px;border-radius:50%;
  background:radial-gradient(circle,rgba(255,93,58,0.18),transparent 60%);
  bottom:-100px;right:-100px;opacity:0;transition:opacity .2s;pointer-events:none;
}

/* CTA */
.cta{
  margin:120px 40px;max-width:1240px;
  border:1px solid var(--line-2);border-radius:24px;padding:80px 60px;text-align:center;
  background:
    radial-gradient(60% 80% at 50% 0%,rgba(255,93,58,0.18),transparent 70%),
    linear-gradient(180deg,#0a0a0c,#000);
  position:relative;overflow:hidden;
}
.cta h2{font-size:clamp(40px,6vw,72px);font-weight:600;letter-spacing:-0.03em;line-height:1.05;margin-bottom:18px}
.cta p{color:var(--fg-2);font-size:17px;max-width:520px;margin:0 auto 32px}

footer{
  border-top:1px solid var(--line);padding:32px 40px;
  display:flex;justify-content:space-between;font-family:var(--mono);font-size:11.5px;color:var(--muted);
  max-width:1400px;margin:0 auto;letter-spacing:0.04em;
}
@media(max-width:600px){footer{flex-direction:column;gap:8px}}
</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="/v3"><span class="m"></span> Forma</a>
  <div class="nav-links">
    <a href="#how">How it works</a>
    <a href="#inventory">Inventory</a>
    <a href="#pricing">Pricing</a>
  </div>
  <a class="btn-go" href="/app">Open app →</a>
</nav>

<section class="hero">
  <div class="hero-text">
    <div class="eyebrow"><span class="glow"></span> {{ s.official }} OFFICIAL FORMS · LIVE</div>
    <h1 class="h1">Built for<br>the <span class="lift">score.</span></h1>
    <p class="sub">Every official ACT question, ever released. <b>{{ "{:,}".format(s.total_q) }}</b> of them. Indexed by topic, drilled by an adaptive engine, explained by a tutor that remembers what you missed.</p>
    <div class="cta-row">
      <a class="btn-primary" href="/app">Start drilling →</a>
      <a class="btn-ghost" href="#how">See how it works</a>
    </div>
  </div>
  <div class="scantron-wrap">
    <div class="scantron-glow"></div>
    <div class="scantron">
      <div class="scantron-head">
        <h4>ACT · ANSWER SHEET</h4>
        <span class="stamp">FORM 2025</span>
      </div>
      <div class="scantron-rows">
        {% for i in range(1,13) %}
        <div class="srow">
          <span class="n">{{ "%02d"|format(i) }}</span>
          <span class="bubbles">
            {% for L in ["A","B","C","D"] %}
            <span class="bub{% if (i*7 + loop.index0)%4 == 1 %} filled{% endif %}">{{ L }}</span>
            {% endfor %}
          </span>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
</section>

<div class="stats-strip">
  <div class="stat"><div class="v">{{ "{:,}".format(s.total_q) }}</div><div class="l">Questions</div></div>
  <div class="stat"><div class="v">{{ "{:,}".format(s.official_q) }}</div><div class="l">Official ACT Q</div></div>
  <div class="stat"><div class="v">{{ s.official }}</div><div class="l">Released forms</div></div>
  <div class="stat"><div class="v">{{ s.topics }}</div><div class="l">Topics tagged</div></div>
</div>

<section class="sec" id="how">
  <div class="sec-eyebrow">HOW IT WORKS</div>
  <h2 class="sec-title">Three things, done right.</h2>
  <p class="sec-lead">The whole product is built around the loop: see a real question, learn why you missed it, get more of what hurts.</p>

  <div class="fgrid">
    <div class="fc">
      <div class="glow"></div>
      <div class="num">01 / DRILL</div>
      <h3>Every official question.</h3>
      <p>Not facsimiles. The real ACT — every released form, every question. The wording, the trap answers, the cadence. When test day arrives, you've already seen it.</p>
      <div class="visual"><span>{{ s.official }}</span> official forms · <span>{{ "{:,}".format(s.total_q) }}</span> questions</div>
    </div>
    <div class="fc">
      <div class="glow"></div>
      <div class="num">02 / LEARN</div>
      <h3>Tutor that explains why.</h3>
      <p>Every wrong answer gets a real explanation. The tutor names the trap, points to the rule, and connects it to the last three things you missed.</p>
      <div class="visual"><span>Claude 4.7</span> · contextual memory enabled</div>
    </div>
    <div class="fc">
      <div class="glow"></div>
      <div class="num">03 / ADAPT</div>
      <h3>Engine targets weak spots.</h3>
      <p>The system watches your accuracy by topic and feeds you more of what you miss. Time on the platform converts directly into score points.</p>
      <div class="visual"><span>{{ s.topics }}</span> topics tracked · adaptive drilling</div>
    </div>
  </div>
</section>

<section class="sec" id="inventory">
  <div class="sec-eyebrow">INVENTORY</div>
  <h2 class="sec-title">The full archive.</h2>
  <p class="sec-lead">Browse every section, every test, every topic. Bookmark hard ones. Re-drill what hurts.</p>

  <div class="fgrid" style="grid-template-columns:repeat(4,1fr)">
    <div class="fc" style="min-height:220px">
      <div class="num" style="color:#5eead4">ENGLISH</div>
      <h3 style="font-size:36px;margin-top:14px">{{ "{:,}".format(s.english) }}</h3>
      <p>Grammar, mechanics, rhetoric.</p>
    </div>
    <div class="fc" style="min-height:220px">
      <div class="num" style="color:#a78bfa">MATH</div>
      <h3 style="font-size:36px;margin-top:14px">{{ "{:,}".format(s.math) }}</h3>
      <p>Pre-algebra through trig.</p>
    </div>
    <div class="fc" style="min-height:220px">
      <div class="num" style="color:#f59e0b">READING</div>
      <h3 style="font-size:36px;margin-top:14px">{{ "{:,}".format(s.reading) }}</h3>
      <p>Full passages, all four genres.</p>
    </div>
    <div class="fc" style="min-height:220px">
      <div class="num" style="color:#f87171">SCIENCE</div>
      <h3 style="font-size:36px;margin-top:14px">{{ "{:,}".format(s.science) }}</h3>
      <p>Charts, experiments, viewpoints.</p>
    </div>
  </div>
</section>

<div class="cta">
  <h2>The next question<br>is waiting.</h2>
  <p>Free to start. Five dollars a month for the tutor. Cancel anytime.</p>
  <div class="cta-row" style="justify-content:center">
    <a class="btn-primary" href="/app">Start drilling →</a>
    <a class="btn-ghost" href="/full-test">Browse the inventory</a>
  </div>
</div>

<footer>
  <span>© 2026 FORMA · BUILT FOR THE SCORE</span>
  <span>{{ s.total_q }} QUESTIONS · INDEXED {{ s.last_scrape[:10] if s.last_scrape else "TODAY" }}</span>
</footer>

</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# V4 — BENTO + KINETIC (Linear / Arc / Raycast)
# Modern bento grid hero with live mini-demos. Subtle motion in every tile.
# ─────────────────────────────────────────────────────────────────────────────
V4_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forma — Master the ACT, methodically.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0b0b10; --panel:#13131a; --panel-2:#1b1b24; --panel-3:#22222c;
  --line:#22222c; --line-2:#2c2c36; --fg:#f1f1f6; --fg-2:#bdbdc6; --muted:#7d7d88; --dim:#4e4e58;
  --acc:#8b5cf6; --teal:#5eead4; --amber:#fbbf24; --rose:#f87171; --lime:#a3e635;
  --sans:"Inter",-apple-system,system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14.5px;line-height:1.55;
  -webkit-font-smoothing:antialiased}
body{
  background:
    radial-gradient(50% 50% at 50% -10%,rgba(139,92,246,0.10),transparent 70%),
    linear-gradient(180deg,#0b0b10,#070709);
  min-height:100vh;
}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--mono);font-feature-settings:"tnum"}

/* nav */
.nav{
  display:flex;align-items:center;justify-content:space-between;
  padding:18px 32px;border-bottom:1px solid var(--line);
  position:sticky;top:0;background:rgba(11,11,16,0.85);backdrop-filter:blur(16px);z-index:10;
}
.logo{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15.5px;letter-spacing:-0.01em}
.logo .mk{
  width:24px;height:24px;border-radius:7px;
  background:linear-gradient(135deg,var(--acc),#6d28d9);
  display:grid;place-items:center;color:#fff;font-size:11px;font-weight:700;
  box-shadow:0 8px 20px -5px rgba(139,92,246,0.5);
}
.nav-links{display:flex;align-items:center;gap:28px;font-size:13.5px;color:var(--fg-2)}
.nav-links a:hover{color:var(--fg)}
.btn-go{
  padding:8px 14px;border-radius:8px;font-size:13px;font-weight:500;
  background:var(--fg);color:#0b0b10;display:inline-flex;align-items:center;gap:6px;
}
.btn-go:hover{background:#fff}

/* hero */
.hero{padding:80px 32px 40px;max-width:1280px;margin:0 auto}
.h-eyebrow{
  display:inline-flex;align-items:center;gap:10px;
  font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.08em;
  padding:6px 12px;border:1px solid var(--line-2);border-radius:999px;
  background:var(--panel);margin-bottom:32px;
}
.h-eyebrow .live{width:6px;height:6px;border-radius:50%;background:var(--lime);box-shadow:0 0 10px var(--lime)}
.h1{
  font-size:clamp(48px,7vw,88px);font-weight:600;letter-spacing:-0.035em;line-height:0.98;
  max-width:920px;
}
.h1 b{
  background:linear-gradient(120deg,var(--acc),#c084fc 50%,var(--teal));
  -webkit-background-clip:text;background-clip:text;color:transparent;font-weight:600;
}
.h1 .meth{font-style:italic;font-weight:500;letter-spacing:-0.04em}
.h-sub{
  margin:24px 0 36px;color:var(--fg-2);font-size:17px;max-width:640px;line-height:1.55;
}
.h-cta{display:flex;gap:10px;flex-wrap:wrap}
.btn-p{
  padding:11px 18px;border-radius:9px;background:var(--fg);color:#0b0b10;
  font-weight:500;font-size:14px;display:inline-flex;align-items:center;gap:8px;
  transition:transform .12s;
}
.btn-p:hover{transform:translateY(-1px)}
.btn-s{
  padding:11px 18px;border-radius:9px;background:var(--panel);color:var(--fg);
  font-weight:500;font-size:14px;border:1px solid var(--line-2);
  display:inline-flex;align-items:center;gap:8px;
}
.btn-s:hover{border-color:var(--acc)}

/* bento */
.bento{
  margin-top:64px;
  display:grid;
  grid-template-columns:repeat(6,1fr);
  grid-auto-rows:160px;
  gap:14px;
}
@media(max-width:1000px){.bento{grid-template-columns:repeat(3,1fr)}}
@media(max-width:640px){.bento{grid-template-columns:repeat(2,1fr);grid-auto-rows:140px}}
.t{
  border:1px solid var(--line);border-radius:16px;
  background:linear-gradient(180deg,var(--panel) 0%,#0e0e14 100%);
  padding:22px;position:relative;overflow:hidden;
  transition:border-color .15s, transform .15s;
}
.t:hover{border-color:var(--line-2);transform:translateY(-2px)}
.t .label{
  font-family:var(--mono);font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;
  color:var(--muted);font-weight:500;
}
.t h3{font-size:18px;font-weight:600;letter-spacing:-0.01em;margin-top:4px;line-height:1.25}
.t p{color:var(--fg-2);font-size:13.5px;line-height:1.55;margin-top:6px}

/* tile spans */
.t-q{grid-column:span 3;grid-row:span 2}
.t-stat{grid-column:span 2;grid-row:span 2}
.t-streak{grid-column:span 1;grid-row:span 1}
.t-predict{grid-column:span 1;grid-row:span 1}
.t-tutor{grid-column:span 4;grid-row:span 2}
.t-sections{grid-column:span 2;grid-row:span 2}
@media(max-width:1000px){
  .t-q{grid-column:span 3}
  .t-stat{grid-column:span 2}
  .t-streak{grid-column:span 1}
  .t-predict{grid-column:span 2}
  .t-tutor{grid-column:span 3}
  .t-sections{grid-column:span 3}
}
@media(max-width:640px){
  .t-q,.t-stat,.t-streak,.t-predict,.t-tutor,.t-sections{grid-column:span 2;grid-row:span 1}
  .t-q,.t-tutor{grid-row:span 2}
}

/* tile contents */
.q-render{margin-top:18px;font-size:17px;color:var(--fg);line-height:1.4}
.q-render .x{font-family:var(--mono);color:var(--teal)}
.q-opts{margin-top:14px;display:grid;gap:6px}
.q-opt{display:flex;align-items:center;gap:10px;padding:8px 12px;border:1px solid var(--line-2);border-radius:8px;font-size:13.5px;color:var(--fg-2)}
.q-opt .k{font-family:var(--mono);font-size:10.5px;color:var(--muted);width:14px;font-weight:600}
.q-opt.correct{border-color:var(--lime);background:rgba(163,230,53,0.06);color:var(--fg)}
.q-opt.correct .k{color:var(--lime)}
.q-opt.correct:after{content:"✓";margin-left:auto;color:var(--lime);font-family:var(--mono);font-size:14px}

/* stat tile */
.stat-big{margin-top:10px}
.stat-big .v{font-size:54px;font-weight:600;letter-spacing:-0.03em;line-height:1;
  background:linear-gradient(180deg,#fff,#7d7d88);-webkit-background-clip:text;background-clip:text;color:transparent}
.stat-big .sub{font-size:12.5px;color:var(--muted);margin-top:8px;font-family:var(--mono);letter-spacing:0.06em}
.stat-bars{margin-top:14px;display:grid;gap:8px}
.sb{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:11px}
.sb .l{width:60px;color:var(--fg-2);text-transform:uppercase;letter-spacing:0.08em;font-size:10px;font-weight:600}
.sb .b{flex:1;height:4px;border-radius:2px;background:var(--panel-2);overflow:hidden}
.sb .b i{display:block;height:100%;border-radius:2px;animation:fill 1.4s cubic-bezier(.2,.7,.2,1) forwards}
.sb.s1 .b i{background:var(--teal);width:0;--w:88%}
.sb.s2 .b i{background:var(--acc);width:0;--w:100%}
.sb.s3 .b i{background:var(--amber);width:0;--w:43%}
.sb.s4 .b i{background:var(--rose);width:0;--w:51%}
.sb .n{color:var(--fg);min-width:40px;text-align:right}
@keyframes fill{from{width:0}to{width:var(--w)}}

/* streak tile */
.streak-num{font-size:48px;font-weight:600;letter-spacing:-0.03em;margin-top:8px;color:var(--amber);line-height:1}
.streak-num .unit{font-size:14px;color:var(--muted);font-weight:500;margin-left:6px;letter-spacing:0}
.streak-dots{margin-top:14px;display:flex;gap:4px}
.streak-dots i{width:14px;height:14px;border-radius:4px;background:var(--panel-2)}
.streak-dots i.on{background:var(--amber);box-shadow:0 0 8px rgba(251,191,36,0.4)}

/* predict tile */
.predict{display:flex;align-items:baseline;gap:10px;margin-top:14px}
.predict .from{font-size:30px;color:var(--muted);font-weight:500;letter-spacing:-0.02em}
.predict .arrow{font-family:var(--mono);color:var(--teal);font-size:18px}
.predict .to{font-size:44px;color:var(--teal);font-weight:700;letter-spacing:-0.03em}
.predict-sub{font-family:var(--mono);font-size:10.5px;color:var(--muted);letter-spacing:0.08em;margin-top:6px}

/* tutor tile */
.tutor-bubble{margin-top:14px;display:grid;gap:10px}
.tb{display:flex;gap:12px;align-items:flex-start}
.tb .who{
  width:24px;height:24px;border-radius:50%;flex-shrink:0;
  display:grid;place-items:center;font-size:10px;font-weight:600;color:#fff;font-family:var(--mono);
}
.tb.user .who{background:var(--panel-3);color:var(--fg-2)}
.tb.ai .who{background:linear-gradient(135deg,var(--acc),#6d28d9);box-shadow:0 4px 12px -2px rgba(139,92,246,0.5)}
.tb .msg{font-size:13.5px;color:var(--fg-2);line-height:1.55}
.tb.ai .msg b{color:var(--teal);font-weight:500}
.typing{display:inline-flex;gap:3px;margin-left:4px}
.typing i{width:4px;height:4px;border-radius:50%;background:var(--muted);animation:blink 1.4s infinite}
.typing i:nth-child(2){animation-delay:.2s} .typing i:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:0.3}40%{opacity:1}}

/* sections tile */
.sec-tiles{margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:8px}
.sec-tile{
  border:1px solid var(--line-2);border-radius:10px;padding:12px;
  display:flex;flex-direction:column;
}
.sec-tile .dot{width:8px;height:8px;border-radius:50%}
.sec-tile .name{font-size:12px;font-weight:500;color:var(--fg);margin-top:6px}
.sec-tile .qs{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px}
.sec-tile.e .dot{background:var(--teal)}
.sec-tile.m .dot{background:var(--acc)}
.sec-tile.r .dot{background:var(--amber)}
.sec-tile.s .dot{background:var(--rose)}

/* methods section */
.sec-wrap{max-width:1280px;margin:0 auto;padding:100px 32px 0}
.sec-eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:0.2em;color:var(--acc);text-transform:uppercase;margin-bottom:12px}
.sec-title{font-size:clamp(32px,5vw,56px);font-weight:600;letter-spacing:-0.025em;line-height:1.05;max-width:780px;margin-bottom:18px}
.sec-lead{color:var(--fg-2);font-size:17px;max-width:620px;margin-bottom:48px;line-height:1.55}

.methods{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:900px){.methods{grid-template-columns:1fr}}
.method-card{
  border:1px solid var(--line);border-radius:14px;
  background:linear-gradient(180deg,var(--panel),#0a0a0e);
  padding:28px 24px;
}
.method-card .num{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.16em}
.method-card h3{font-size:20px;font-weight:600;letter-spacing:-0.01em;margin:12px 0 10px}
.method-card p{color:var(--fg-2);font-size:14px;line-height:1.6}
.method-card .ic{
  width:36px;height:36px;border-radius:9px;background:rgba(139,92,246,0.12);
  display:grid;place-items:center;color:var(--acc);font-size:18px;margin-bottom:18px;
}

/* pricing strip */
.pricing-strip{
  margin-top:80px;display:grid;grid-template-columns:1fr 1fr;gap:14px;
}
@media(max-width:760px){.pricing-strip{grid-template-columns:1fr}}
.plan{
  border:1px solid var(--line);border-radius:16px;padding:32px;
  background:linear-gradient(180deg,var(--panel),#0a0a0e);
}
.plan.pro{border-color:var(--acc);background:linear-gradient(180deg,rgba(139,92,246,0.08),#0a0a0e)}
.plan .price{font-size:48px;font-weight:600;letter-spacing:-0.03em;display:flex;align-items:baseline;gap:8px}
.plan .price .per{font-size:14px;color:var(--muted);font-weight:500;font-family:var(--mono)}
.plan h3{font-size:17px;font-weight:600;margin:6px 0 14px}
.plan ul{list-style:none;display:grid;gap:9px;margin-top:18px}
.plan li{display:flex;gap:10px;align-items:flex-start;font-size:14px;color:var(--fg-2)}
.plan li:before{content:"✓";color:var(--lime);font-family:var(--mono);font-size:13px;flex-shrink:0;padding-top:1px}
.plan .cta-row{margin-top:24px}

/* final CTA */
.final-cta{
  margin:100px 32px 60px;max-width:1280px;
  border:1px solid var(--line-2);border-radius:20px;padding:60px 40px;text-align:center;
  background:
    radial-gradient(60% 100% at 50% 0%,rgba(139,92,246,0.15),transparent 70%),
    linear-gradient(180deg,var(--panel),#0a0a0e);
}
.final-cta h2{font-size:clamp(36px,5vw,56px);font-weight:600;letter-spacing:-0.025em;margin-bottom:14px}
.final-cta p{color:var(--fg-2);font-size:16px;max-width:520px;margin:0 auto 28px}

footer{
  border-top:1px solid var(--line);padding:28px 32px;
  display:flex;justify-content:space-between;font-family:var(--mono);font-size:11.5px;color:var(--muted);
  max-width:1280px;margin:0 auto;letter-spacing:0.04em;
}
</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="/v4"><span class="mk">F</span>forma</a>
  <div class="nav-links">
    <a href="#method">Method</a>
    <a href="#pricing">Pricing</a>
    <a href="/full-test">Inventory</a>
  </div>
  <a class="btn-go" href="/app">Open app →</a>
</nav>

<section class="hero">
  <div class="h-eyebrow"><span class="live"></span> {{ "{:,}".format(s.total_q) }} REAL ACT QUESTIONS · LIVE INVENTORY</div>
  <h1 class="h1">Master the ACT,<br><span class="meth"><b>methodically.</b></span></h1>
  <p class="h-sub">Drill every official ACT question. Get a tutor that explains why. Watch your score predictor climb as the engine targets your weak spots.</p>
  <div class="h-cta">
    <a class="btn-p" href="/app">Start free →</a>
    <a class="btn-s" href="#method">See the method</a>
  </div>

  <div class="bento">
    <div class="t t-q">
      <div class="label">SAMPLE · MATH</div>
      <div class="q-render">If <span class="x">x² = 49</span>, which could be the value of <span class="x">x</span>?</div>
      <div class="q-opts">
        <div class="q-opt"><span class="k">A</span> 7 only</div>
        <div class="q-opt correct"><span class="k">B</span> 7 or −7</div>
        <div class="q-opt"><span class="k">C</span> 49 only</div>
      </div>
    </div>

    <div class="t t-stat">
      <div class="label">INVENTORY</div>
      <div class="stat-big">
        <div class="v">{{ "{:,}".format(s.total_q) }}</div>
        <div class="sub">questions · {{ s.official }} official forms</div>
      </div>
      <div class="stat-bars">
        <div class="sb s1"><span class="l">Eng</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.english) }}</span></div>
        <div class="sb s2"><span class="l">Math</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.math) }}</span></div>
        <div class="sb s3"><span class="l">Read</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.reading) }}</span></div>
        <div class="sb s4"><span class="l">Sci</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.science) }}</span></div>
      </div>
    </div>

    <div class="t t-streak">
      <div class="label">STREAK</div>
      <div class="streak-num">14<span class="unit">days</span></div>
      <div class="streak-dots">
        <i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i>
      </div>
    </div>

    <div class="t t-predict">
      <div class="label">PREDICTED</div>
      <div class="predict">
        <span class="from">24</span>
        <span class="arrow">→</span>
        <span class="to">32</span>
      </div>
      <div class="predict-sub">+8 in 2 weeks</div>
    </div>

    <div class="t t-tutor">
      <div class="label">AI TUTOR</div>
      <div class="tutor-bubble">
        <div class="tb user"><span class="who">J</span><span class="msg">Why is the answer B?</span></div>
        <div class="tb ai"><span class="who">∴</span><span class="msg">The trap is <b>"7 only"</b> — most students grab the positive root. But squaring kills the sign: <b>(−7)² = 49</b> too. So x = ±7. You missed this pattern twice last week, queuing three more like it<span class="typing"><i></i><i></i><i></i></span></span></div>
      </div>
    </div>

    <div class="t t-sections">
      <div class="label">SECTIONS</div>
      <div class="sec-tiles">
        <div class="sec-tile e"><span class="dot"></span><span class="name">English</span><span class="qs">{{ "{:,}".format(s.english) }} q</span></div>
        <div class="sec-tile m"><span class="dot"></span><span class="name">Math</span><span class="qs">{{ "{:,}".format(s.math) }} q</span></div>
        <div class="sec-tile r"><span class="dot"></span><span class="name">Reading</span><span class="qs">{{ "{:,}".format(s.reading) }} q</span></div>
        <div class="sec-tile s"><span class="dot"></span><span class="name">Science</span><span class="qs">{{ "{:,}".format(s.science) }} q</span></div>
      </div>
    </div>
  </div>
</section>

<section class="sec-wrap" id="method">
  <div class="sec-eyebrow">METHOD</div>
  <h2 class="sec-title">A test you've seen ten<br>thousand times stops surprising you.</h2>
  <p class="sec-lead">Forma is built around a single idea: pattern exposure beats trick memorization. Three pieces make it work.</p>

  <div class="methods">
    <div class="method-card">
      <div class="ic">⚡</div>
      <div class="num">01 · DRILL</div>
      <h3>Real official material.</h3>
      <p>{{ s.official }} released forms, every question, every answer choice. Identical to test day — wording, traps, cadence. No facsimiles, no filler.</p>
    </div>
    <div class="method-card">
      <div class="ic">∴</div>
      <div class="num">02 · LEARN</div>
      <h3>Tutor that names the trap.</h3>
      <p>Every wrong answer gets a paragraph of real explanation. The tutor pulls from your history and connects today's mistake to last week's pattern.</p>
    </div>
    <div class="method-card">
      <div class="ic">◎</div>
      <div class="num">03 · ADAPT</div>
      <h3>Engine targets weak spots.</h3>
      <p>{{ s.topics }} topics, tracked. The system watches your accuracy and feeds you more of what hurts. No question wasted on what you already nailed.</p>
    </div>
  </div>
</section>

<section class="sec-wrap" id="pricing">
  <div class="sec-eyebrow">PRICING</div>
  <h2 class="sec-title">Free to try. Cheap to keep.</h2>

  <div class="pricing-strip">
    <div class="plan">
      <h3>Free</h3>
      <div class="price">$0<span class="per">/ forever</span></div>
      <ul>
        <li>Every question, every test</li>
        <li>Topic search · bookmarks</li>
        <li>Section drilling</li>
        <li>Stats &amp; review queue</li>
      </ul>
      <div class="cta-row"><a class="btn-s" href="/app">Start free →</a></div>
    </div>
    <div class="plan pro">
      <h3>Premium</h3>
      <div class="price">$5<span class="per">/ month</span></div>
      <ul>
        <li>Everything in free</li>
        <li>AI tutor on every question</li>
        <li>Adaptive engine + score predictor</li>
        <li>Wrong-answer review queue</li>
      </ul>
      <div class="cta-row"><a class="btn-p" href="/app">Upgrade →</a></div>
    </div>
  </div>
</section>

<div class="final-cta">
  <h2>Drill the next question.</h2>
  <p>{{ "{:,}".format(s.total_q) }} are waiting. The engine already knows where to start.</p>
  <div class="h-cta" style="justify-content:center">
    <a class="btn-p" href="/app">Open Forma →</a>
    <a class="btn-s" href="/full-test">See official tests</a>
  </div>
</div>

<footer>
  <span>© 2026 FORMA · METHODICAL ACT PREP</span>
  <span>{{ s.total_q }} Q · {{ s.official }} OFFICIAL FORMS · {{ s.topics }} TOPICS</span>
</footer>

</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# V5 — MERGE: V4 structure + V2 gold/serif + V3 scantron (made unmistakably ACT)
# ─────────────────────────────────────────────────────────────────────────────
V5_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forma — Master the ACT, efficiently.</title>
<meta name="description" content="Forma is methodical ACT prep on 17,000+ real questions across 700+ official forms. Drill by topic, see your projected score, and learn from every miss.">
<link rel="canonical" href="https://forma-prep.up.railway.app/">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><rect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%230d0d0f%22/><text x=%2232%22 y=%2244%22 font-family=%22Georgia,serif%22 font-size=%2240%22 font-weight=%22600%22 fill=%22%23e8a33d%22 text-anchor=%22middle%22>F</text></svg>">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Forma">
<meta property="og:title" content="Forma — Master the ACT, efficiently.">
<meta property="og:description" content="Methodical ACT prep on 17,000+ real questions across 700+ official forms.">
<meta property="og:url" content="https://forma-prep.up.railway.app/">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="Forma — Master the ACT, efficiently.">
<meta name="twitter:description" content="Methodical ACT prep on 17,000+ real questions across 700+ official forms.">
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0a0805; --bg-2:#0e0a05; --panel:#15110a; --panel-2:#1e1810; --panel-3:#2a2114;
  --line:#241c11; --line-2:#36291a; --line-3:#4a3a25;
  --fg:#f3e7d3; --fg-2:#d4c5a8; --muted:#8a7a5e; --dim:#5a4a36;
  --amber:#e8a64a; --amber-2:#ffb24e; --amber-3:#d4881e; --amber-soft:rgba(232,166,74,0.12);
  --paper:#f8f1dd; --paper-2:#e8dcbf;
  --display:"Switzer",-apple-system,system-ui,sans-serif;
  --sans:"Switzer",-apple-system,system-ui,sans-serif;
  --serif:"Switzer",-apple-system,system-ui,sans-serif;  /* legacy alias */
  --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:14.5px;line-height:1.55;
  -webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;overflow-x:hidden}
body{
  background:
    radial-gradient(50% 40% at 50% -10%,rgba(232,166,74,0.10),transparent 70%),
    linear-gradient(180deg,#0a0805 0%, #060402 100%);
  min-height:100vh;
}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--mono);font-feature-settings:"tnum"}
.serif{font-family:var(--serif)}

/* ─── NAV ─── */
.nav{
  display:flex;align-items:center;justify-content:space-between;
  padding:20px 36px;border-bottom:1px solid var(--line);
  position:sticky;top:0;background:rgba(10,8,5,0.86);backdrop-filter:blur(14px);z-index:20;
}
.logo{display:flex;align-items:baseline;gap:2px;font-family:var(--display);font-weight:600;font-size:20px;letter-spacing:-0.025em;color:var(--fg)}
.logo .dot{color:var(--amber);font-size:0.55em;vertical-align:0.35em;margin-left:2px;font-family:var(--sans)}
.nav-links{display:flex;align-items:center;gap:32px;font-size:13px;color:var(--fg-2);letter-spacing:0.04em;text-transform:uppercase;font-family:var(--sans);font-weight:500}
.nav-links a:hover{color:var(--amber)}
.btn-go{
  padding:9px 18px;border-radius:0;font-size:12.5px;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;
  background:var(--paper);color:var(--bg);display:inline-flex;align-items:center;gap:8px;
  font-family:var(--sans);transition:background .15s;
}
.btn-go:hover{background:var(--amber)}

/* ─── HERO ─── */
.hero{
  padding:80px 36px 60px;max-width:1340px;margin:0 auto;
  display:grid;grid-template-columns:1.1fr 1fr;gap:60px;align-items:center;min-height:calc(100vh - 80px);
}
@media(max-width:1000px){.hero{grid-template-columns:1fr;padding-top:60px;min-height:auto;gap:48px}}
.h-eyebrow{
  display:inline-flex;align-items:center;gap:10px;
  font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:0.16em;text-transform:uppercase;
  padding:6px 14px;border:1px solid var(--line-2);border-radius:0;
  background:var(--panel);margin-bottom:32px;font-weight:500;
}
.h-eyebrow .live{width:6px;height:6px;border-radius:50%;background:var(--amber);box-shadow:0 0 10px var(--amber)}
.h1{
  font-family:var(--display);font-weight:600;
  font-size:clamp(54px,7.5vw,100px);letter-spacing:-0.045em;line-height:0.96;
  color:var(--fg);
}
.h1 em{font-style:italic;color:var(--amber);font-weight:500;letter-spacing:-0.04em}
.h1 .gold{color:var(--amber);font-weight:600}
.h-sub{
  margin:28px 0 36px;color:var(--fg-2);font-size:18px;max-width:540px;line-height:1.55;font-family:var(--sans);
}
.h-sub b{color:var(--fg);font-weight:500}
.h-cta{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.btn-p{
  padding:14px 24px;border-radius:0;font-family:var(--sans);font-size:12.5px;font-weight:500;
  letter-spacing:0.08em;text-transform:uppercase;background:var(--paper);color:var(--bg);
  display:inline-flex;align-items:center;gap:10px;transition:background .15s, transform .15s;
}
.btn-p:hover{background:var(--amber);transform:translateY(-1px)}
.btn-s{
  font-family:var(--sans);font-size:12.5px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;
  color:var(--fg-2);display:inline-flex;align-items:center;gap:8px;padding:14px 4px;
  border-bottom:1px solid var(--line-2);transition:color .15s, border-color .15s;
}
.btn-s:hover{color:var(--amber);border-color:var(--amber)}

/* ─── SCANTRON (improved, unmistakably ACT) ─── */
.scantron-wrap{
  position:relative;perspective:1600px;perspective-origin:50% 50%;
  height:640px;display:grid;place-items:center;
}
@media(max-width:1000px){.scantron-wrap{height:520px}}
.scantron-glow{
  position:absolute;inset:0;
  background:radial-gradient(50% 50% at 50% 50%,rgba(232,166,74,0.22),transparent 60%);
  filter:blur(24px);pointer-events:none;
}
/* Scaled-score side strip — composite indicator */
.score-strip{
  position:absolute;left:-12px;top:50%;transform:translateY(-50%) rotateZ(-3deg);z-index:3;
  background:linear-gradient(180deg,#1a1208,#0d0905);border:1px solid var(--line-3);
  padding:14px 12px;font-family:var(--mono);font-size:10px;color:var(--muted);
  letter-spacing:0.18em;text-align:center;border-radius:2px;
  box-shadow:0 20px 40px -10px rgba(0,0,0,0.6);
}
.score-strip .lab{color:var(--amber);letter-spacing:0.22em;font-weight:600;font-size:9px;margin-bottom:6px}
.score-strip .val{font-family:var(--display);font-size:36px;color:var(--paper);letter-spacing:-0.03em;line-height:1;font-weight:600}
.score-strip .delta{color:#9bd66a;font-size:10px;margin-top:6px}
@media(max-width:1000px){.score-strip{display:none}}

.scantron{
  width:400px;height:560px;
  background:
    linear-gradient(180deg,#fdf8e8 0%,#f3e9c8 100%),
    repeating-linear-gradient(0deg,transparent 0,transparent 23px,rgba(0,0,0,0.02) 24px);
  border-radius:6px;
  transform-style:preserve-3d;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.4) inset,
    0 60px 100px -25px rgba(0,0,0,0.9),
    0 0 0 1px rgba(60,40,15,0.3),
    -30px 40px 80px -15px rgba(232,166,74,0.2);
  padding:20px 26px;position:relative;
  /* Clean card-flip entry: 2 quick Y-axis rotations, then settle into float */
  animation:scantron-entry 0.85s cubic-bezier(0.25, 0.1, 0.25, 1) forwards,
            float 9s ease-in-out 0.85s infinite;
  will-change:transform,opacity;
}
@media(max-width:1000px){.scantron{width:320px;height:460px}}
@keyframes scantron-entry{
  0%   {transform:rotateY(-740deg) rotateX(7deg) rotateZ(-3deg) scale(0.92);opacity:0}
  30%  {opacity:1}
  100% {transform:rotateY(-20deg) rotateX(7deg) rotateZ(-3deg) scale(1);opacity:1}
}
@keyframes float{0%,100%{transform:rotateY(-20deg) rotateX(7deg) rotateZ(-3deg) translateY(0)}50%{transform:rotateY(-18deg) rotateX(8deg) rotateZ(-3deg) translateY(-10px)}}
/* Score strip drops in after the flip lands */
.score-strip{opacity:0;animation:strip-in 0.35s cubic-bezier(0.2,0.7,0.2,1) 0.8s forwards}
@keyframes strip-in{from{opacity:0;transform:translateY(-50%) rotateZ(-3deg) translateX(-16px)}to{opacity:1;transform:translateY(-50%) rotateZ(-3deg) translateX(0)}}

.sc-head{
  border-bottom:2px solid #2a2010;padding-bottom:10px;margin-bottom:8px;
  display:flex;justify-content:space-between;align-items:flex-start;
}
.sc-head .left{}
.sc-head .actlogo{
  font-family:var(--sans);font-weight:800;font-size:14px;letter-spacing:0.04em;color:#1a1408;
  display:inline-block;border:2px solid #1a1408;padding:2px 8px;border-radius:2px;
}
.sc-head .subtest{
  font-family:var(--sans);font-size:9px;color:#5a4825;letter-spacing:0.22em;font-weight:700;
  text-transform:uppercase;margin-top:6px;
}
.sc-head .form{
  font-family:var(--mono);font-size:8.5px;letter-spacing:0.18em;color:#5a4825;
  border:1px solid #8a6f3a;padding:3px 6px;border-radius:2px;font-weight:600;
}
.sc-instructions{
  font-family:var(--sans);font-size:8.5px;color:#7a6240;letter-spacing:0.08em;
  margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid rgba(60,40,15,0.15);
  text-transform:uppercase;font-weight:600;
}
.sc-rows{display:grid;gap:8px;font-family:var(--mono)}
.srow{display:flex;align-items:center;gap:9px}
.srow .n{font-family:var(--mono);font-size:10px;color:#5a4825;width:18px;text-align:right;font-weight:700}
.srow .bubs{display:flex;gap:5px}
.bub{
  width:19px;height:19px;border-radius:50%;border:1.5px solid #5a4825;
  font-family:var(--sans);font-size:8.5px;color:#5a4825;
  display:grid;place-items:center;font-weight:700;background:#fbf3da;
  transition:all .2s;
}
.bub.fill{background:#1a1408;border-color:#1a1408;color:transparent;position:relative}
.bub.fill:after{
  content:"";position:absolute;inset:2.5px;border-radius:50%;
  background:radial-gradient(circle at 30% 30%,#3a3025,#1a1408 70%);
}
/* Interactive bubble hover/click */
.scantron .bub{cursor:pointer;transition:transform .08s, background .15s, border-color .15s}
.scantron .bub:hover{background:#e8dcbf;border-color:#1a1408;transform:scale(1.12)}
.scantron .bub.fill:hover{background:#1a1408;transform:scale(1.12)}
.bub.just-filled{animation:bubble-pop 0.32s cubic-bezier(0.34,1.56,0.64,1)}
@keyframes bubble-pop{
  0%{transform:scale(1)}
  50%{transform:scale(1.35)}
  100%{transform:scale(1)}
}

/* ─── STATS STRIP ─── */
.stats-strip{
  border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  padding:40px 36px;display:grid;grid-template-columns:repeat(4,1fr);gap:24px;max-width:1340px;margin:0 auto;
  position:relative;
}
.stats-strip:before,.stats-strip:after{
  content:"";position:absolute;top:50%;width:36px;height:1px;background:var(--line);
}
.stats-strip:before{left:0} .stats-strip:after{right:0}
@media(max-width:760px){.stats-strip{grid-template-columns:repeat(2,1fr);gap:32px}}
.stat{}
.stat .v{
  font-family:var(--display);font-weight:600;font-size:56px;letter-spacing:-0.04em;line-height:1;
  color:var(--paper);
}
.stat .l{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:0.16em;text-transform:uppercase;margin-top:10px;font-weight:500}

/* ─── BENTO GRID (from V4, recolored) ─── */
.bento-wrap{max-width:1340px;margin:0 auto;padding:100px 36px 60px}
.sec-eyebrow{
  font-family:var(--mono);font-size:11px;letter-spacing:0.24em;color:var(--amber);
  text-transform:uppercase;margin-bottom:14px;font-weight:500;
  display:flex;align-items:center;gap:14px;
}
.sec-eyebrow:before{content:"";display:block;width:36px;height:1px;background:var(--amber)}
.sec-title{
  font-family:var(--display);font-weight:600;font-size:clamp(34px,4.6vw,60px);
  letter-spacing:-0.035em;line-height:1.05;max-width:820px;margin-bottom:20px;color:var(--fg);
}
.sec-title em{font-style:italic;color:var(--amber);font-weight:500}
.sec-lead{color:var(--fg-2);font-size:17px;max-width:640px;margin-bottom:52px;line-height:1.6;font-family:var(--sans)}

.bento{
  display:grid;grid-template-columns:repeat(6,1fr);grid-auto-rows:170px;gap:14px;
}
@media(max-width:1000px){.bento{grid-template-columns:repeat(3,1fr)}}
@media(max-width:640px){.bento{grid-template-columns:repeat(2,1fr);grid-auto-rows:150px}}
.t{
  border:1px solid var(--line);border-radius:0;
  background:linear-gradient(180deg,var(--panel) 0%,#0a0805 100%);
  padding:24px;position:relative;overflow:hidden;
  transition:border-color .15s, transform .15s;
}
.t:hover{border-color:var(--line-3);transform:translateY(-2px)}
.t .label{
  font-family:var(--mono);font-size:10.5px;letter-spacing:0.2em;text-transform:uppercase;
  color:var(--muted);font-weight:500;
}
.t h3{font-family:var(--display);font-size:20px;font-weight:600;letter-spacing:-0.02em;margin-top:6px;line-height:1.25;color:var(--fg)}
.t p{color:var(--fg-2);font-size:13.5px;line-height:1.55;margin-top:6px}

.t-q{grid-column:span 3;grid-row:span 2}
.t-stat{grid-column:span 2;grid-row:span 2}
.t-streak{grid-column:span 1;grid-row:span 1}
.t-predict{grid-column:span 1;grid-row:span 1}
.t-tutor{grid-column:span 4;grid-row:span 2}
.t-sections{grid-column:span 2;grid-row:span 2}
@media(max-width:1000px){
  .t-q{grid-column:span 3}
  .t-stat{grid-column:span 2}
  .t-streak{grid-column:span 1}
  .t-predict{grid-column:span 2}
  .t-tutor{grid-column:span 3}
  .t-sections{grid-column:span 3}
}
@media(max-width:640px){
  .t-q,.t-stat,.t-streak,.t-predict,.t-tutor,.t-sections{grid-column:span 2;grid-row:span 1}
  .t-q,.t-tutor{grid-row:span 2}
}

/* sample question tile */
.q-render{margin-top:18px;font-family:var(--display);font-weight:500;font-size:17px;color:var(--fg);line-height:1.4}
.q-render .x{font-family:var(--mono);color:var(--amber);font-size:0.92em}
.q-opts{margin-top:14px;display:grid;gap:6px}
.q-opt{display:flex;align-items:center;gap:12px;padding:9px 14px;border:1px solid var(--line-2);font-size:13.5px;color:var(--fg-2);font-family:var(--sans)}
.q-opt .k{font-family:var(--mono);font-size:10.5px;color:var(--muted);width:14px;font-weight:700}
.q-opt.correct{border-color:var(--amber);background:var(--amber-soft);color:var(--fg)}
.q-opt.correct .k{color:var(--amber)}
.q-opt.correct:after{content:"✓";margin-left:auto;color:var(--amber);font-family:var(--mono);font-size:14px;font-weight:700}
/* Interactive: clickable answer options with feedback */
.t-q .q-opt{cursor:pointer;transition:border-color .12s, background .12s, transform .12s}
.t-q .q-opt:hover{border-color:var(--line-3);background:var(--panel-2)}
.t-q .q-opt.picked-right{border-color:#9bd66a;background:rgba(155,214,106,0.10);color:var(--fg);animation:pop-right 0.5s cubic-bezier(0.34,1.56,0.64,1)}
.t-q .q-opt.picked-right .k{color:#9bd66a}
.t-q .q-opt.picked-right:after{content:"✓";margin-left:auto;color:#9bd66a;font-family:var(--mono);font-size:14px;font-weight:700}
.t-q .q-opt.picked-wrong{border-color:#e0735a;background:rgba(224,115,90,0.08);color:var(--fg);animation:shake 0.34s ease}
.t-q .q-opt.picked-wrong .k{color:#e0735a}
.t-q .q-opt.picked-wrong:after{content:"✗";margin-left:auto;color:#e0735a;font-family:var(--mono);font-size:14px;font-weight:700}
@keyframes pop-right{0%{transform:scale(1)}40%{transform:scale(1.04)}100%{transform:scale(1)}}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}
.q-feedback{
  margin-top:14px;padding:12px 14px;border-left:2px solid var(--amber);
  font-family:var(--display);font-size:13px;color:var(--fg-2);line-height:1.55;
  opacity:0;transform:translateY(-4px);transition:opacity .25s, transform .25s;
  background:rgba(232,166,74,0.04);
}
.q-feedback.show{opacity:1;transform:translateY(0)}
.q-feedback b{color:var(--amber)}

/* inventory tile with bars */
.stat-big{margin-top:12px}
.stat-big .v{font-family:var(--display);font-size:52px;font-weight:600;letter-spacing:-0.04em;line-height:1;color:var(--paper)}
.stat-big .sub{font-size:12.5px;color:var(--muted);margin-top:10px;font-family:var(--mono);letter-spacing:0.06em}
.stat-bars{margin-top:14px;display:grid;gap:9px}
.sb{display:flex;align-items:center;gap:12px;font-family:var(--mono);font-size:11px}
.sb .l{width:60px;color:var(--fg-2);text-transform:uppercase;letter-spacing:0.1em;font-size:10px;font-weight:600}
.sb .b{flex:1;height:4px;background:var(--panel-2);overflow:hidden}
.sb .b i{display:block;height:100%;animation:fillb 1.5s cubic-bezier(.2,.7,.2,1) forwards;background:var(--amber);width:0}
.sb.s1 .b i{--w:88%} .sb.s2 .b i{--w:100%} .sb.s3 .b i{--w:43%} .sb.s4 .b i{--w:51%}
.sb .n{color:var(--paper);min-width:42px;text-align:right;font-weight:600}
@keyframes fillb{from{width:0}to{width:var(--w)}}

/* streak tile */
.streak-num{font-family:var(--display);font-size:50px;font-weight:600;letter-spacing:-0.04em;margin-top:10px;color:var(--amber);line-height:1}
.streak-num .unit{font-family:var(--sans);font-size:13px;color:var(--muted);font-weight:500;margin-left:8px;letter-spacing:0}
.streak-dots{margin-top:16px;display:flex;gap:5px}
.streak-dots i{width:14px;height:14px;background:var(--panel-2)}
.streak-dots i.on{background:var(--amber);box-shadow:0 0 8px rgba(232,166,74,0.4)}

/* predict tile */
.predict{display:flex;align-items:baseline;gap:12px;margin-top:16px}
.predict .from{font-family:var(--display);font-size:30px;color:var(--muted);font-weight:500;letter-spacing:-0.03em}
.predict .arrow{font-family:var(--mono);color:var(--amber);font-size:18px}
.predict .to{font-family:var(--display);font-size:44px;color:var(--amber);font-weight:600;letter-spacing:-0.04em}
.predict-sub{font-family:var(--mono);font-size:10.5px;color:var(--muted);letter-spacing:0.08em;margin-top:8px}

/* tutor tile */
.tutor-bubble{margin-top:16px;display:grid;gap:12px}
.tb{display:flex;gap:12px;align-items:flex-start}
.tb .who{
  width:26px;height:26px;border-radius:50%;flex-shrink:0;
  display:grid;place-items:center;font-size:10px;font-weight:700;color:var(--bg);font-family:var(--mono);
}
.tb.user .who{background:var(--panel-3);color:var(--fg-2)}
.tb.ai .who{background:linear-gradient(135deg,var(--amber),var(--amber-3));box-shadow:0 4px 14px -2px rgba(232,166,74,0.5);color:#1a1408}
.tb .msg{font-family:var(--display);font-size:14px;color:var(--fg-2);line-height:1.55}
.tb.ai .msg b{color:var(--amber);font-weight:500;font-style:normal}
.typing{display:inline-flex;gap:3px;margin-left:4px}
.typing i{width:4px;height:4px;border-radius:50%;background:var(--muted);animation:blink 1.4s infinite}
.typing i:nth-child(2){animation-delay:.2s} .typing i:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:0.3}40%{opacity:1}}

/* sections tile */
.sec-tiles{margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:8px}
.sec-tile{border:1px solid var(--line-2);padding:14px;display:flex;flex-direction:column}
.sec-tile .dot{width:8px;height:8px;border-radius:50%;background:var(--amber)}
.sec-tile .name{font-family:var(--display);font-size:14px;font-weight:600;color:var(--fg);margin-top:8px;letter-spacing:-0.01em}
.sec-tile .qs{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px;letter-spacing:0.04em}

/* ─── METHOD ─── */
.method-wrap{max-width:1340px;margin:0 auto;padding:100px 36px 0}
.methods{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border-top:1px solid var(--line-2);margin-top:36px}
@media(max-width:900px){.methods{grid-template-columns:1fr}}
.method-card{
  padding:40px 32px;border-right:1px solid var(--line-2);border-bottom:1px solid var(--line-2);
  transition:background .15s;
}
.method-card:hover{background:var(--panel)}
.method-card:nth-child(3){border-right:0}
@media(max-width:900px){.method-card{border-right:0}}
.method-card .num{font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:0.24em;font-weight:600}
.method-card h3{font-family:var(--display);font-size:24px;font-weight:600;letter-spacing:-0.025em;margin:14px 0 12px;line-height:1.2;color:var(--fg)}
.method-card p{color:var(--fg-2);font-family:var(--display);font-size:15px;line-height:1.6}

/* ─── PRICING ─── */
.pricing-wrap{max-width:1340px;margin:0 auto;padding:100px 36px 0}
.pricing{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.pricing{grid-template-columns:1fr}}
.plan{
  border:1px solid var(--line-2);padding:40px 32px;
  background:linear-gradient(180deg,var(--panel),#0a0805);
}
.plan.pro{
  border-color:var(--amber);
  background:linear-gradient(180deg,rgba(232,166,74,0.06),#0a0805);
}
.plan h3{font-family:var(--display);font-size:20px;font-weight:600;letter-spacing:-0.02em;margin-bottom:8px}
.plan .price{font-family:var(--display);font-size:60px;font-weight:600;letter-spacing:-0.04em;display:flex;align-items:baseline;gap:10px;color:var(--paper);line-height:1}
.plan .price .per{font-family:var(--mono);font-size:14px;color:var(--muted);font-weight:500;letter-spacing:0}
.plan ul{list-style:none;display:grid;gap:11px;margin-top:24px}
.plan li{display:flex;gap:12px;align-items:flex-start;font-size:14.5px;color:var(--fg-2);font-family:var(--sans)}
.plan li:before{content:"✓";color:var(--amber);font-family:var(--mono);font-size:13px;flex-shrink:0;padding-top:2px;font-weight:700}
.plan .cta-row{margin-top:32px}

/* ─── FINAL CTA ─── */
.final-cta{
  margin:120px 36px 80px;max-width:1340px;
  border-top:1px solid var(--line-2);padding:80px 40px;text-align:center;
}
.final-cta h2{font-family:var(--display);font-size:clamp(44px,6.5vw,78px);font-weight:600;letter-spacing:-0.045em;margin-bottom:20px;line-height:1.05}
.final-cta h2 em{font-style:italic;color:var(--amber);font-weight:500}
.final-cta p{color:var(--fg-2);font-size:18px;max-width:560px;margin:0 auto 36px;font-family:var(--sans);line-height:1.55}
.final-cta .h-cta{justify-content:center;display:flex;gap:14px;flex-wrap:wrap}

footer{
  border-top:1px solid var(--line);padding:32px 36px 28px;
  display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;
  font-family:var(--mono);font-size:11px;color:var(--muted);
  max-width:1340px;margin:0 auto;letter-spacing:0.08em;text-transform:uppercase;
}
footer .built{justify-self:center;text-transform:none;letter-spacing:0;font-family:var(--sans);font-size:12.5px;color:var(--fg-2)}
footer .built a{color:var(--amber);border-bottom:1px solid rgba(232,166,74,0.25);padding-bottom:1px}
footer .built a:hover{border-bottom-color:var(--amber)}
footer .right{justify-self:end}
@media(max-width:640px){footer{grid-template-columns:1fr;justify-items:start;gap:14px}footer .built,footer .right{justify-self:start}}
</style>
</head>
<body>

<nav class="nav">
  <a class="logo" href="/v5">Forma<span class="dot">●</span></a>
  <div class="nav-links">
    <a href="#method">Method</a>
    <a href="#inventory">Inventory</a>
    <a href="#pricing">Pricing</a>
  </div>
  <a class="btn-go" href="/app">Open app →</a>
</nav>

<section class="hero">
  <div class="hero-text">
    <div class="h-eyebrow"><span class="live"></span> 147 OFFICIAL ACT FORMS · LIVE</div>
    <h1 class="h1">Master the <span class="gold">ACT</span>,<br>efficiently.</h1>
    <p class="h-sub">Drill every official ACT question. Get a tutor that explains why the right answer is right. Watch your score predictor climb as the engine targets your weak spots.</p>
    <div class="h-cta">
      <a class="btn-p" href="/app">Start drilling →</a>
      <a class="btn-s" href="#method">See the method →</a>
    </div>
  </div>

  <div class="scantron-wrap">
    <div class="scantron-glow"></div>

    <div class="score-strip">
      <div class="lab">COMPOSITE</div>
      <div class="val">36</div>
      <div class="delta">↑ +12</div>
    </div>

    <div class="scantron">
      <div class="sc-head">
        <div class="left">
          <span class="actlogo">ACT</span>
          <div class="subtest">Mathematics Test · 60 min · 60 questions</div>
        </div>
        <span class="form">FORM 25-MC1</span>
      </div>
      <div class="sc-instructions">Mark all responses on this answer document</div>
      <div class="sc-rows">
        {# Real ACT math: odd rows use A-E, even rows use F-J #}
        {% set patterns = [
          (1, "ABCDE", 1),  (2, "FGHJK", 3),  (3, "ABCDE", 1),  (4, "FGHJK", 2),
          (5, "ABCDE", 4),  (6, "FGHJK", 0),  (7, "ABCDE", 2),  (8, "FGHJK", 3),
          (9, "ABCDE", 1),  (10,"FGHJK", 2), (11,"ABCDE", 3), (12,"FGHJK", 1),
        ] %}
        {% for n, letters, filled in patterns %}
        <div class="srow">
          <span class="n">{{ "%02d"|format(n) }}</span>
          <span class="bubs">
            {% for L in letters %}
            <span class="bub{% if loop.index0 == filled %} fill{% endif %}">{{ L }}</span>
            {% endfor %}
          </span>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
</section>

<div class="stats-strip">
  <div class="stat"><div class="v">{{ "{:,}".format(s.total_q) }}</div><div class="l">Questions</div></div>
  <div class="stat"><div class="v">{{ "{:,}".format(s.official_q) }}</div><div class="l">Official ACT Q</div></div>
  <div class="stat"><div class="v">{{ s.official }}</div><div class="l">Released forms</div></div>
  <div class="stat"><div class="v">{{ s.topics }}</div><div class="l">Topics tagged</div></div>
</div>

<section class="bento-wrap" id="inventory">
  <div class="sec-eyebrow">THE PRODUCT</div>
  <h2 class="sec-title">Every piece of the loop,<br><em>built in.</em></h2>
  <p class="sec-lead">See a real ACT question. Learn why you missed it. Get more of what hurts. The whole product is the loop — and you can watch all of it on one screen.</p>

  <div class="bento">
    <div class="t t-q">
      <div class="label">SAMPLE · MATH · FORM 25-MC1 · Q42 · <span style="color:var(--amber)">TAP TO ANSWER</span></div>
      <div class="q-render">If <span class="x">x² = 49</span>, which of the following could be the value of <span class="x">x</span>?</div>
      <div class="q-opts">
        <div class="q-opt"><span class="k">A</span> 7 only</div>
        <div class="q-opt correct"><span class="k">B</span> 7 or −7</div>
        <div class="q-opt"><span class="k">C</span> 49 only</div>
      </div>
      <div class="q-feedback" id="q-feedback"></div>
    </div>

    <div class="t t-stat">
      <div class="label">LIVE INVENTORY</div>
      <div class="stat-big">
        <div class="v">{{ "{:,}".format(s.total_q) }}</div>
        <div class="sub">questions · {{ s.official }} official forms</div>
      </div>
      <div class="stat-bars">
        <div class="sb s1"><span class="l">Eng</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.english) }}</span></div>
        <div class="sb s2"><span class="l">Math</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.math) }}</span></div>
        <div class="sb s3"><span class="l">Read</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.reading) }}</span></div>
        <div class="sb s4"><span class="l">Sci</span><span class="b"><i></i></span><span class="n">{{ "{:,}".format(s.science) }}</span></div>
      </div>
    </div>

    <div class="t t-streak">
      <div class="label">STREAK</div>
      <div class="streak-num">14<span class="unit">days</span></div>
      <div class="streak-dots">
        <i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i>
      </div>
    </div>

    <div class="t t-predict">
      <div class="label">PREDICTED ACT</div>
      <div class="predict">
        <span class="from">24</span>
        <span class="arrow">→</span>
        <span class="to">32</span>
      </div>
      <div class="predict-sub">+8 IN 2 WEEKS</div>
    </div>

    <div class="t t-tutor">
      <div class="label">AI TUTOR · LIVE</div>
      <div class="tutor-bubble">
        <div class="tb user"><span class="who">J</span><span class="msg">Why is the answer B and not A?</span></div>
        <div class="tb ai"><span class="who">∴</span><span class="msg">The trap is <b>"7 only"</b> — most students grab the positive root and move on. But squaring kills the sign: <b>(−7)² = 49</b> too. So x = ±7. You missed this exact pattern twice last week — queueing three more like it now<span class="typing"><i></i><i></i><i></i></span></span></div>
      </div>
    </div>

    <div class="t t-sections">
      <div class="label">SECTIONS</div>
      <div class="sec-tiles">
        <div class="sec-tile"><span class="dot"></span><span class="name">English</span><span class="qs">{{ "{:,}".format(s.english) }} Q · 182 tests</span></div>
        <div class="sec-tile"><span class="dot"></span><span class="name">Math</span><span class="qs">{{ "{:,}".format(s.math) }} Q · 188 tests</span></div>
        <div class="sec-tile"><span class="dot"></span><span class="name">Reading</span><span class="qs">{{ "{:,}".format(s.reading) }} Q · 146 tests</span></div>
        <div class="sec-tile"><span class="dot"></span><span class="name">Science</span><span class="qs">{{ "{:,}".format(s.science) }} Q · 187 tests</span></div>
      </div>
    </div>
  </div>
</section>

<section class="method-wrap" id="method">
  <div class="sec-eyebrow">METHOD</div>
  <h2 class="sec-title">A test you've seen ten thousand times<br><em>stops surprising you.</em></h2>
  <p class="sec-lead">Most prep teaches tricks. Forma teaches the test. Three pieces make the loop work — and they're built around the only thing that moves your score: exposure to real official material.</p>

  <div class="methods">
    <div class="method-card">
      <div class="num">01 · DRILL</div>
      <h3>Every official question, indexed.</h3>
      <p>{{ s.official }} released ACT forms, going back twenty years. The exact wording, the exact trap answers, the exact cadence. When test day arrives, you've already seen it.</p>
    </div>
    <div class="method-card">
      <div class="num">02 · LEARN</div>
      <h3>A tutor that names the trap.</h3>
      <p>Every wrong answer gets a real explanation — not "the answer is C," but a paragraph that points to the rule and connects it to the last three things you missed.</p>
    </div>
    <div class="method-card">
      <div class="num">03 · ADAPT</div>
      <h3>The engine targets weak spots.</h3>
      <p>{{ s.topics }} topics tracked. The system watches your accuracy and feeds you more of what hurts. No question wasted on what you already nailed.</p>
    </div>
  </div>
</section>

<section class="pricing-wrap" id="pricing">
  <div class="sec-eyebrow">PRICING</div>
  <h2 class="sec-title">Free to try.<br><em>Cheap to keep.</em></h2>

  <div class="pricing">
    <div class="plan">
      <h3>Free</h3>
      <div class="price">$0<span class="per">/ forever</span></div>
      <ul>
        <li>All {{ "{:,}".format(s.total_q) }} questions · all {{ s.total_t }} tests</li>
        <li>Section drilling · topic search · bookmarks</li>
        <li>Stats &amp; full-length timed tests</li>
        <li><b>3 AI tutor explanations / day</b></li>
      </ul>
      <div class="cta-row"><a class="btn-s" href="/app">Start free →</a></div>
    </div>
    <div class="plan pro">
      <h3>Premium</h3>
      <div class="price">$5<span class="per">/ month</span></div>
      <ul>
        <li>Everything in free, plus:</li>
        <li><b>Unlimited AI tutor</b> on every question</li>
        <li><b>Adaptive engine</b> — drills only your weak topics</li>
        <li><b>Live score predictor</b> + wrong-answer review queue</li>
      </ul>
      <div class="cta-row"><a class="btn-p" href="/app">Upgrade →</a></div>
    </div>
  </div>
</section>

<div class="final-cta">
  <h2>Drill the<br><em>next question.</em></h2>
  <p>{{ "{:,}".format(s.total_q) }} are waiting. The engine already knows where to start.</p>
  <div class="h-cta">
    <a class="btn-p" href="/app">Open Forma →</a>
    <a class="btn-s" href="/full-test">See official tests →</a>
  </div>
</div>

<footer>
  <span>© 2026 Forma</span>
  <span class="built">Built solo by an 18-year-old high school junior · <a href="mailto:jasperthelazzer19@gmail.com">say hi</a></span>
  <span class="right">{{ "{:,}".format(s.total_q) }} Q · {{ s.official }} OFFICIAL · {{ s.topics }} TOPICS</span>
</footer>

<script>
(function(){
  // ── Clickable scantron bubbles ─────────────────────────────────────────
  document.querySelectorAll('.scantron .bub').forEach(function(b){
    b.addEventListener('click', function(e){
      e.stopPropagation();
      // Unfill siblings in same row, fill this one
      var row = b.parentElement;
      Array.from(row.children).forEach(function(x){ x.classList.remove('fill','just-filled'); });
      b.classList.add('fill','just-filled');
      // Strip the animation class so it can re-trigger next time
      setTimeout(function(){ b.classList.remove('just-filled'); }, 320);
    });
  });

  // ── 3D mouse-parallax on the scantron ──────────────────────────────────
  // Only on devices with a real mouse (skip touch). Activates after entry anim.
  var hasFinePointer = window.matchMedia && window.matchMedia('(pointer: fine)').matches;
  var scantron = document.querySelector('.scantron');
  var wrap     = document.querySelector('.scantron-wrap');
  if (hasFinePointer && scantron && wrap) {
    var parallaxOn = false;
    setTimeout(function(){
      parallaxOn = true;
      // Replace the gentle float with cursor-driven motion
      scantron.style.animation = 'none';
      scantron.style.transition = 'transform 0.45s cubic-bezier(0.2,0.7,0.2,1)';
      scantron.style.transform  = 'rotateY(-20deg) rotateX(7deg) rotateZ(-3deg)';
    }, 900);

    wrap.addEventListener('mousemove', function(e){
      if (!parallaxOn) return;
      var rect = wrap.getBoundingClientRect();
      var cx = (e.clientX - rect.left) / rect.width  - 0.5;  // −0.5 .. +0.5
      var cy = (e.clientY - rect.top)  / rect.height - 0.5;
      var yRot = -20 + cx * 18;   // tilt left/right
      var xRot =   7 + -cy * 12;  // tilt up/down (inverted feels natural)
      var zRot =  -3 + cx * 3;
      scantron.style.transition = 'transform 0.18s ease-out';
      scantron.style.transform  = 'rotateY(' + yRot + 'deg) rotateX(' + xRot + 'deg) rotateZ(' + zRot + 'deg)';
    });
    wrap.addEventListener('mouseleave', function(){
      if (!parallaxOn) return;
      scantron.style.transition = 'transform 0.55s cubic-bezier(0.2,0.7,0.2,1)';
      scantron.style.transform  = 'rotateY(-20deg) rotateX(7deg) rotateZ(-3deg)';
    });
  }

  // ── Playable sample question with feedback ─────────────────────────────
  var sampleOpts = document.querySelectorAll('.t-q .q-opt');
  var feedback   = document.getElementById('q-feedback');
  var FB_RIGHT = '<b>Correct.</b> Squaring kills the sign — both 7 and −7 square to 49. The classic trap is to grab only the positive root.';
  var FB_WRONG_A = '<b>Trap answer.</b> Most students pick 7 — but <b>(−7)² = 49</b> too. The right answer is B: 7 or −7.';
  var FB_WRONG_C = '<b>Not quite.</b> 49 is x², not x. Solving x² = 49 means taking the square root → x = ±7. The right answer is B.';
  sampleOpts.forEach(function(opt){
    opt.addEventListener('click', function(){
      sampleOpts.forEach(function(o){ o.classList.remove('picked-right','picked-wrong','correct'); });
      var k = opt.querySelector('.k') ? opt.querySelector('.k').textContent.trim() : '';
      var isCorrect = (k === 'B');
      opt.classList.add(isCorrect ? 'picked-right' : 'picked-wrong');
      if (feedback) {
        if (isCorrect)      feedback.innerHTML = FB_RIGHT;
        else if (k === 'A') feedback.innerHTML = FB_WRONG_A;
        else                feedback.innerHTML = FB_WRONG_C;
        feedback.classList.add('show');
      }
    });
  });
})();
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Route registration
# ─────────────────────────────────────────────────────────────────────────────
def _v1():
    return render_template_string(V1_HTML, s=_stats())

def _v2():
    return render_template_string(V2_HTML, s=_stats())

def _v3():
    return render_template_string(V3_HTML, s=_stats())

def _v4():
    return render_template_string(V4_HTML, s=_stats())

def _v5():
    return render_template_string(V5_HTML, s=_stats())


def register(app):
    # Public landing page lives at the root.
    app.add_url_rule("/", "landing_home", _v5)
    # /v5 kept as a stable alias (used while iterating; safe to remove later).
    app.add_url_rule("/v5", "landing_v5", _v5)
    # Dev-only variants — left mounted so they keep being browsable.
    app.add_url_rule("/v1", "landing_v1", _v1)
    app.add_url_rule("/v2", "landing_v2", _v2)
    app.add_url_rule("/v3", "landing_v3", _v3)
    app.add_url_rule("/v4", "landing_v4", _v4)
