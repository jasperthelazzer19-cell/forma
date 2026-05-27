"""UI shell — colors, fonts, layout templates, section labels.

All in-app pages use these constants. The landing page (forma/landing.py)
has its own scoped styles to keep its aesthetic from leaking into the app.
"""

SECTION_LABELS = {
    "english":  "English",
    "math":     "Math",
    "reading":  "Reading",
    "science":  "Science",
}

BASE_CSS = """
:root {
  /* ─── FORMA palette: warm dark + gold (matches V5 landing) ─── */
  --bg: #0a0805;
  --panel: #15110a;
  --panel-2: #1e1810;
  --panel-3: #2a2114;
  --fg: #f3e7d3;
  --fg-2: #d4c5a8;
  --muted: #8a7a5e;
  --dim: #5a4a36;
  --border: #241c11;
  --border-strong: #36291a;
  --accent: #e8a64a;
  --accent-dim: #d4881e;
  --accent-glow: rgba(232,166,74,0.18);
  --accent-soft: rgba(232,166,74,0.10);
  --teal: #5eead4;
  --amber: #fbbf24;
  --green: #9bd66a;
  --good: #9bd66a;
  --bad: #e0735a;
  --paper: #f8f1dd;
  --sans: "Switzer", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  --serif: "Switzer", Georgia, serif;
  --display: "Switzer", -apple-system, system-ui, sans-serif;
  /* compat aliases — legacy templates use these names */
  --bg-2: var(--panel);
  --bg-3: var(--panel-2);
  --bg-4: var(--panel-3);
  --accent-dim2: rgba(232,166,74,0.65);
  --accent-warm: #fbbf24;
  --purple: #c4a4ff;
  --shadow-soft: 0 1px 0 rgba(255,255,255,0.02) inset;
  --shadow-hover: 0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 28px rgba(232,166,74,0.10);
  --shadow-deep: 0 12px 30px rgba(0,0,0,0.35);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: var(--bg); color: var(--fg); }
body {
  font-family: var(--sans);
  font-size: 13px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
}
a { color: var(--accent); text-decoration: none; transition: color .12s; }
a:hover { color: var(--fg); }
::selection { background: var(--accent-soft); color: var(--fg); }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.14); }
.mono { font-family: var(--mono); }
.muted { color: var(--muted); }
.dim { color: var(--dim); }
.kbd {
  font-family: var(--mono); font-size: 10px;
  padding: 1px 6px; border: 1px solid var(--border-strong); border-radius: 4px;
  background: var(--bg); color: var(--muted); line-height: 1.5;
}

/* ─── APP SHELL — sidebar + main canvas ─── */
.app { display: grid; grid-template-columns: 232px 1fr; min-height: 100vh; }
@media (max-width: 740px) { .app { grid-template-columns: 1fr; } .sb { display: none; } }
.sb {
  background: var(--bg);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}
.sb-top { padding: 14px 14px 4px; }
.ws {
  display: flex; align-items: center; gap: 9px;
  padding: 6px 8px; border-radius: 6px;
  cursor: default;
}
.ws-icon {
  width: 22px; height: 22px; border-radius: 6px;
  background: linear-gradient(135deg, var(--accent) 0%, #b8821e 100%);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #1a1408;
  font-family: var(--display);
  letter-spacing: -0.02em;
  box-shadow: 0 6px 16px -4px rgba(232,166,74,0.4);
}
.ws-name { font-weight: 600; font-size: 14px; flex: 1; color: var(--fg); font-family: var(--display); letter-spacing: -0.01em; }
.ws-chev { color: var(--muted); font-size: 10px; }
.sb-search {
  margin: 10px 14px 14px;
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel); cursor: text;
  transition: border-color .12s;
}
.sb-search:hover { border-color: var(--border-strong); }
.sb-search-ic { color: var(--dim); font-size: 11px; }
.sb-search-label {
  background: transparent; border: 0; outline: 0; color: var(--muted);
  font-family: inherit; font-size: 12.5px; flex: 1; padding: 0; user-select: none;
}
.sb-section { padding: 6px 8px; }
.sb-section-label {
  font-size: 9.5px; color: var(--dim); letter-spacing: 0.06em; text-transform: uppercase;
  padding: 8px 10px 4px; font-weight: 600;
}
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 5px 10px; margin: 1px 0; border-radius: 5px;
  color: var(--muted); cursor: pointer; font-size: 13px;
  text-decoration: none; line-height: 1.6;
  transition: background .12s, color .12s;
}
.nav-item:hover { background: var(--panel); color: var(--fg); text-decoration: none; }
.nav-item.active { background: var(--panel-2); color: var(--fg); }
.nav-item .ic { width: 14px; flex-shrink: 0; opacity: 0.9; font-size: 12px; text-align: center; display: inline-block; }
.nav-item .count { margin-left: auto; font-size: 10.5px; color: var(--dim); font-family: var(--mono); }
.nav-item .dot {
  width: 6px; height: 6px; border-radius: 50%;
  display: inline-block; flex-shrink: 0;
}
.sb-foot {
  margin-top: auto; padding: 12px 14px; border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
}
.avatar {
  width: 22px; height: 22px; border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
  display: flex; align-items: center; justify-content: center;
  color: white; font-weight: 700; font-size: 10px;
}
.you { font-size: 12.5px; color: var(--fg); }

/* ─── MAIN canvas ─── */
.main { display: flex; flex-direction: column; min-width: 0; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 22px; height: 44px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  position: sticky; top: 0; z-index: 30;
}
.crumbs { color: var(--muted); font-size: 12.5px; display: flex; gap: 6px; align-items: center; }
.crumbs .sep { color: var(--dim); }
.crumbs b { color: var(--fg); font-weight: 500; }
.top-actions { display: flex; align-items: center; gap: 8px; }
.canvas { padding: 28px 36px 60px; max-width: 1180px; width: 100%; }
.wrap { padding: 28px 36px 60px; max-width: 1180px; width: 100%; margin: 0 auto; }
@media (max-width: 740px) { .canvas, .wrap { padding: 20px; } }

h1 {
  font-family: var(--sans); font-weight: 600; font-size: 22px;
  margin: 0 0 6px; letter-spacing: -0.012em; line-height: 1.2;
}
h2 {
  font-family: var(--sans); font-weight: 600; font-size: 14px;
  margin: 28px 0 10px; letter-spacing: -0.004em;
  color: var(--fg);
}
.subtitle { color: var(--muted); font-size: 13px; margin-bottom: 22px; }

/* ─── Buttons ─── */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 6px;
  background: var(--accent); color: white;
  border: 0; font-family: inherit; font-size: 12px; font-weight: 500;
  cursor: pointer; text-decoration: none;
  transition: background .12s, border-color .12s;
}
.btn:hover { background: var(--accent-dim); text-decoration: none; color: white; }
.btn.ghost {
  background: transparent; color: var(--muted);
  border: 1px solid var(--border-strong);
}
.btn.ghost:hover { color: var(--fg); border-color: #3a3a44; background: var(--panel); }
.btn.lg { padding: 9px 16px; font-size: 13px; }

/* ─── Cards / panels ─── */
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px 20px;
  transition: border-color .12s;
}
.card:hover { border-color: var(--border-strong); }
.hr { height: 1px; background: var(--border); margin: 22px 0; border: 0; }

/* ─── Cmd-K palette ─── */
.palette-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  display: none; align-items: flex-start; justify-content: center;
  padding-top: 12vh; backdrop-filter: blur(4px); z-index: 100;
}
.palette-overlay.open { display: flex; }
.palette {
  width: 580px; max-width: 90%;
  background: rgba(20,20,26,0.97); border: 1px solid var(--border-strong);
  border-radius: 10px; overflow: hidden;
  box-shadow: 0 30px 80px rgba(0,0,0,0.6);
}
.palette input {
  width: 100%; background: transparent; border: 0; outline: 0; color: var(--fg);
  padding: 16px 18px; font-family: inherit; font-size: 14px;
  border-bottom: 1px solid var(--border);
}
.palette input::placeholder { color: var(--muted); }
.palette-section-label {
  font-size: 10px; color: var(--dim); letter-spacing: 0.16em; text-transform: uppercase;
  padding: 10px 16px 4px; font-weight: 600;
}
.palette-results { max-height: 50vh; overflow-y: auto; padding-bottom: 6px; }
.palette-item {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; cursor: pointer; font-size: 13px;
  color: var(--fg-2); text-decoration: none;
}
.palette-item:hover, .palette-item.on { background: var(--accent-soft); color: var(--fg); }
.palette-item .pi { font-size: 13px; width: 16px; text-align: center; color: var(--muted); }
.palette-item:hover .pi, .palette-item.on .pi { color: var(--accent); }
.palette-item .pname { flex: 1; }
.palette-item .pmeta { color: var(--dim); font-size: 11.5px; font-family: var(--mono); }
"""

HEAD = """<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Forma</title>
<link rel="preconnect" href="https://api.fontshare.com" crossorigin>
<link rel="preconnect" href="https://cdn.fontshare.com" crossorigin>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{css}{extra_css}</style></head>"""

SIDEBAR_TMPL = """<aside class="sb">
  <div class="sb-top">
    <div class="ws">
      <div class="ws-icon">F</div>
      <div class="ws-name">Forma</div>
      <div class="ws-chev">▾</div>
    </div>
  </div>
  <div class="sb-search" onclick="openPalette()">
    <span class="sb-search-ic">⌕</span>
    <span class="sb-search-label">Search…</span>
    <span class="kbd">⌘K</span>
  </div>
  <div class="sb-section">
    <div class="sb-section-label">Workspace</div>
    <a class="nav-item {a_home}" href="/app"><span class="ic">⌂</span>Today</a>
    <a class="nav-item {a_full}" href="/full-test"><span class="ic">⏱</span>Full tests</a>
    <a class="nav-item {a_topics}" href="/topics"><span class="ic">◆</span>Topics</a>
    <a class="nav-item {a_review}" href="/review"><span class="ic">⟳</span>Review</a>
    <a class="nav-item {a_adaptive}" href="/adaptive"><span class="ic">◎</span>Adaptive</a>
    <a class="nav-item {a_dashboard}" href="/dashboard"><span class="ic">▤</span>Stats</a>
    <a class="nav-item {a_search}" href="/search"><span class="ic">⌕</span>Search</a>
  </div>
  <div class="sb-section">
    <div class="sb-section-label">Sections</div>
    <a class="nav-item {a_english}" href="/section/english"><span class="dot" style="background:#5eead4"></span>English<span class="count">{c_english}</span></a>
    <a class="nav-item {a_math}" href="/section/math"><span class="dot" style="background:#a78bfa"></span>Math<span class="count">{c_math}</span></a>
    <a class="nav-item {a_reading}" href="/section/reading"><span class="dot" style="background:#f59e0b"></span>Reading<span class="count">{c_reading}</span></a>
    <a class="nav-item {a_science}" href="/section/science"><span class="dot" style="background:#f87171"></span>Science<span class="count">{c_science}</span></a>
  </div>
  <div class="sb-section">
    <div class="sb-section-label">Libraries</div>
    <a class="nav-item {a_official}" href="/official"><span class="ic">★</span>Official forms</a>
    <a class="nav-item {a_generated}" href="/generated"><span class="ic">◇</span>AI-generated</a>
  </div>
  <div class="sb-foot">
    <div class="avatar">J</div>
    <div class="you">Jasper</div>
  </div>
</aside>"""

PALETTE_HTML = """<div class="palette-overlay" id="palette" onclick="if(event.target===this)closePalette()">
  <div class="palette">
    <input id="palette-input" placeholder="Type to search drills, sections, or jump to a page…" />
    <div class="palette-section-label">Jump to</div>
    <div class="palette-results" id="palette-results">
      <a class="palette-item on" href="/app"><span class="pi">⌂</span><span class="pname">Today</span><span class="pmeta">G H</span></a>
      <a class="palette-item" href="/full-test"><span class="pi">⏱</span><span class="pname">Full tests</span><span class="pmeta">G F</span></a>
      <a class="palette-item" href="/review"><span class="pi">⟳</span><span class="pname">Review wrong answers</span><span class="pmeta">G R</span></a>
      <a class="palette-item" href="/adaptive"><span class="pi">◎</span><span class="pname">Adaptive practice</span><span class="pmeta">G A</span></a>
      <a class="palette-item" href="/dashboard"><span class="pi">▤</span><span class="pname">Stats &amp; dashboard</span><span class="pmeta">G S</span></a>
      <a class="palette-item" href="/search"><span class="pi">⌕</span><span class="pname">Search questions</span><span class="pmeta">G /</span></a>
      <a class="palette-item" href="/section/english"><span class="pi">●</span><span class="pname">English drills</span><span class="pmeta">1</span></a>
      <a class="palette-item" href="/section/math"><span class="pi">●</span><span class="pname">Math drills</span><span class="pmeta">2</span></a>
      <a class="palette-item" href="/section/reading"><span class="pi">●</span><span class="pname">Reading drills</span><span class="pmeta">3</span></a>
      <a class="palette-item" href="/section/science"><span class="pi">●</span><span class="pname">Science drills</span><span class="pmeta">4</span></a>
    </div>
  </div>
</div>
<script>
function openPalette(){var p=document.getElementById('palette');p.classList.add('open');setTimeout(function(){document.getElementById('palette-input').focus()},20);}
function closePalette(){document.getElementById('palette').classList.remove('open');document.getElementById('palette-input').value='';filterPalette('');}
function filterPalette(q){q=q.toLowerCase();var items=document.querySelectorAll('.palette-item');var first=null;items.forEach(function(it){var t=it.textContent.toLowerCase();var hit=!q||t.indexOf(q)>=0;it.style.display=hit?'flex':'none';if(hit&&!first)first=it;});items.forEach(function(it){it.classList.remove('on');});if(first)first.classList.add('on');}
document.addEventListener('keydown',function(e){
  var p=document.getElementById('palette');
  if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();if(p.classList.contains('open'))closePalette();else openPalette();}
  else if(e.key==='Escape'&&p.classList.contains('open')){closePalette();}
  else if(e.key==='Enter'&&p.classList.contains('open')){var on=p.querySelector('.palette-item.on');if(on)window.location.href=on.getAttribute('href');}
});
document.addEventListener('input',function(e){if(e.target.id==='palette-input')filterPalette(e.target.value);});
</script>"""


def shell_sidebar(active=None, counts=None):
    counts = counts or {}
    active = active or ""
    keys = ["home","full","topics","review","adaptive","dashboard","search",
            "english","math","reading","science","official","generated"]
    cls = {f"a_{k}": ("active" if active == k else "") for k in keys}
    cls["c_english"] = counts.get("english", "")
    cls["c_math"]    = counts.get("math", "")
    cls["c_reading"] = counts.get("reading", "")
    cls["c_science"] = counts.get("science", "")
    return SIDEBAR_TMPL.format(**cls)
