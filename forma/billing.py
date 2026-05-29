"""Accounts + Stripe subscription billing for Forma.

Forma is browsable without an account. Accounts exist so people can pay for
Premium ($5/mo): unlimited AI tutor + adaptive engine + review queue. Free users
get 3 AI-tutor explanations/day (tracked by cookie, no account needed).

Env vars (set in Railway):
  STRIPE_PAYMENT_LINK   — a Stripe Payment Link in SUBSCRIPTION mode ($5/mo)
  STRIPE_WEBHOOK_SECRET — signing secret for /stripe/webhook
  SECRET_KEY            — Flask session signing (set in app.py)
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, date
from functools import wraps

from flask import request, session, redirect, jsonify, make_response

from forma.db import DB_PATH, db

STRIPE_PAYMENT_LINK = os.environ.get("STRIPE_PAYMENT_LINK", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
FREE_TUTOR_PER_DAY = 3

_PAGE_CSS = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;
justify-content:center;background:#0a0805;color:#e8e3d8;font-family:system-ui,-apple-system,sans-serif;padding:24px}
.card{width:100%;max-width:420px;background:#15110a;border:1px solid #2a2114;border-radius:16px;padding:34px}
h1{font-family:Georgia,serif;font-size:1.7rem;margin:0 0 6px}
p.sub{color:#9a8f7a;margin:0 0 22px;font-size:.95rem;line-height:1.5}
label{display:block;font-size:.8rem;color:#9a8f7a;margin:14px 0 5px;letter-spacing:.02em}
input{width:100%;padding:11px 13px;border-radius:9px;border:1px solid #2a2114;background:#0e0a05;color:#e8e3d8;font-size:1rem}
input:focus{outline:none;border-color:#e8a33d}
.btn{display:inline-block;width:100%;text-align:center;margin-top:20px;padding:12px;border:0;border-radius:9px;
background:#e8a33d;color:#1a1206;font-weight:600;font-size:1rem;cursor:pointer;text-decoration:none}
.btn:hover{background:#f0b357}
.alt{margin-top:18px;text-align:center;font-size:.9rem;color:#9a8f7a}
.alt a{color:#e8a33d;text-decoration:none}
.err{background:rgba(220,80,80,.12);border:1px solid rgba(220,80,80,.4);color:#f0a0a0;
padding:10px 12px;border-radius:8px;font-size:.88rem;margin:0 0 16px}
ul.perks{list-style:none;padding:0;margin:18px 0;line-height:1.9}
ul.perks li{padding-left:22px;position:relative}
ul.perks li:before{content:"✓";position:absolute;left:0;color:#e8a33d;font-weight:700}
.price{font-size:2.4rem;font-weight:700;font-family:Georgia,serif}.price span{font-size:1rem;color:#9a8f7a;font-weight:400}
a.back{color:#9a8f7a;text-decoration:none;font-size:.85rem}
"""


def _shell(title, body):
    return (f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · Forma</title>
<meta name="robots" content="noindex"><style>{_PAGE_CSS}</style></head>
<body><div class="card">{body}</div></body></html>""")


# ─── schema ─────────────────────────────────────────────────────────────────
def init_billing_tables():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA busy_timeout=8000")
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            is_paid INTEGER DEFAULT 0,
            stripe_customer_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS tutor_usage (
            ukey TEXT NOT NULL,
            day  TEXT NOT NULL,
            n    INTEGER DEFAULT 0,
            PRIMARY KEY (ukey, day)
        )""")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f" * billing table init skipped: {e}", flush=True)


# ─── password + session helpers ─────────────────────────────────────────────
def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    row = db().execute("SELECT id, email, is_paid, stripe_customer_id FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


def is_premium():
    u = current_user()
    return bool(u and u.get("is_paid"))


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not current_user():
            return redirect("/login?next=" + (request.path or "/app"))
        return f(*a, **k)
    return w


def premium_required(label="This feature"):
    """Decorator factory: gate a route behind Premium with an upgrade page."""
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = current_user()
            if not u:
                return redirect("/login?next=" + (request.path or "/app"))
            if not u.get("is_paid"):
                return _shell("Premium", f"""
                  <a class="back" href="/app">← back</a>
                  <h1>{label} is Premium</h1>
                  <p class="sub">Forma Premium is $5/month — unlimited AI tutor, the adaptive engine, and your review queue.</p>
                  <a class="btn" href="/upgrade">Upgrade — $5/mo →</a>
                  <p class="alt">Free includes all questions + 3 AI explanations/day.</p>""")
            return f(*a, **k)
        return w
    return deco


# ─── AI-tutor daily free limit (cookie-based, no account needed) ─────────────
def _tutor_key():
    """Identify the user for the daily free counter: account id if logged in,
    else a persistent cookie."""
    u = current_user()
    if u:
        return f"u{u['id']}", None
    # Reuse a vid already on the cookie, or one minted earlier in THIS request —
    # otherwise allowance() and record_tutor_use() would mint different ids and
    # the counter would never accumulate.
    vid = request.cookies.get("fv_id") or getattr(request, "_fv_id", None)
    new = None
    if not vid:
        vid = secrets.token_urlsafe(12)
        request._fv_id = vid
        new = vid
    return f"c{vid}", new


def tutor_allowance():
    """Return (allowed: bool, remaining: int|None, set_cookie: str|None).
    Premium users are unlimited (remaining=None)."""
    if is_premium():
        return True, None, None
    key, new_cookie = _tutor_key()
    today = date.today().isoformat()
    row = db().execute("SELECT n FROM tutor_usage WHERE ukey=? AND day=?", (key, today)).fetchone()
    used = row["n"] if row else 0
    return (used < FREE_TUTOR_PER_DAY), max(0, FREE_TUTOR_PER_DAY - used), new_cookie


def record_tutor_use():
    if is_premium():
        return
    key, _ = _tutor_key()
    today = date.today().isoformat()
    conn = db()
    conn.execute("""INSERT INTO tutor_usage(ukey, day, n) VALUES(?,?,1)
                    ON CONFLICT(ukey, day) DO UPDATE SET n = n + 1""", (key, today))
    conn.commit()


# ─── routes ──────────────────────────────────────────────────────────────────
def _safe_next():
    nxt = request.args.get("next") or request.form.get("next") or "/app"
    return nxt if nxt.startswith("/") and "\n" not in nxt and "\r" not in nxt else "/app"


def signup():
    nxt = _safe_next()
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        if not email or "@" not in email or len(pw) < 8:
            return _shell("Sign up", _signup_form(nxt, "Enter a valid email and a password of 8+ characters."))
        salt = secrets.token_hex(16)
        try:
            conn = db()
            cur = conn.execute("INSERT INTO users(email, password_hash, password_salt) VALUES(?,?,?)",
                               (email, _hash(pw, salt), salt))
            conn.commit()
            session["uid"] = cur.lastrowid
        except sqlite3.IntegrityError:
            return _shell("Sign up", _signup_form(nxt, "That email already has an account. Try logging in."))
        return redirect(nxt)
    return _shell("Sign up", _signup_form(nxt))


def _signup_form(nxt, err=""):
    e = f'<div class="err">{err}</div>' if err else ""
    return f"""<a class="back" href="/app">← back</a><h1>Create your account</h1>
    <p class="sub">Free forever, with 3 AI explanations a day. Upgrade any time.</p>{e}
    <form method="post" action="/signup?next={nxt}">
      <label>Email</label><input name="email" type="email" autocomplete="email" required>
      <label>Password</label><input name="password" type="password" autocomplete="new-password" minlength="8" required>
      <button class="btn" type="submit">Create account</button>
    </form>
    <p class="alt">Already have one? <a href="/login?next={nxt}">Log in</a></p>"""


def login():
    nxt = _safe_next()
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        row = db().execute("SELECT id, password_hash, password_salt FROM users WHERE email=?", (email,)).fetchone()
        if not row or _hash(pw, row["password_salt"]) != row["password_hash"]:
            return _shell("Log in", _login_form(nxt, "Wrong email or password."))
        session["uid"] = row["id"]
        return redirect(nxt)
    return _shell("Log in", _login_form(nxt))


def _login_form(nxt, err=""):
    e = f'<div class="err">{err}</div>' if err else ""
    return f"""<a class="back" href="/app">← back</a><h1>Welcome back</h1>
    <p class="sub">Log in to Forma.</p>{e}
    <form method="post" action="/login?next={nxt}">
      <label>Email</label><input name="email" type="email" autocomplete="email" required>
      <label>Password</label><input name="password" type="password" autocomplete="current-password" required>
      <button class="btn" type="submit">Log in</button>
    </form>
    <p class="alt">New here? <a href="/signup?next={nxt}">Create an account</a></p>"""


def logout():
    session.pop("uid", None)
    return redirect("/")


def upgrade():
    u = current_user()
    if not u:
        return redirect("/signup?next=/upgrade")
    if u.get("is_paid"):
        return _shell("Premium", """<a class="back" href="/app">← back</a>
          <h1>You're Premium 🎉</h1><p class="sub">Unlimited AI tutor, the adaptive engine, and your review queue are all unlocked.</p>
          <a class="btn" href="/app">Open Forma →</a>""")
    if not STRIPE_PAYMENT_LINK:
        return _shell("Premium", """<a class="back" href="/app">← back</a>
          <h1>Premium isn't live yet</h1><p class="sub">Checkout isn't configured. Check back soon.</p>""")
    sep = "&" if "?" in STRIPE_PAYMENT_LINK else "?"
    pay = f"{STRIPE_PAYMENT_LINK}{sep}client_reference_id={u['id']}&prefilled_email={u['email']}"
    return _shell("Upgrade", f"""<a class="back" href="/app">← back</a>
      <h1>Forma Premium</h1>
      <div class="price">$5<span>/month</span></div>
      <ul class="perks">
        <li>Unlimited AI tutor on every question</li>
        <li>Adaptive engine — drills only your weak topics</li>
        <li>Live score predictor + wrong-answer review queue</li>
        <li>Everything in Free stays free</li>
      </ul>
      <a class="btn" href="{pay}">Subscribe — $5/mo →</a>
      <p class="alt">Secure checkout via Stripe · cancel any time.</p>""")


def upgrade_thanks():
    u = current_user()
    if u and u.get("is_paid"):
        return _shell("Premium", """<h1>You're Premium 🎉</h1>
          <p class="sub">Everything's unlocked. Thanks for supporting Forma.</p>
          <a class="btn" href="/app">Open Forma →</a>""")
    return _shell("Almost there", """<h1>Payment received — activating…</h1>
      <p class="sub">This takes a few seconds. Refresh, or head back to the app — Premium unlocks automatically.</p>
      <a class="btn" href="/app">Open Forma →</a>
      <p class="alt">Not unlocked after a minute? Log in with the email you paid with.</p>""")


def api_account():
    u = current_user()
    return jsonify({"logged_in": bool(u), "email": u["email"] if u else None,
                    "premium": bool(u and u["is_paid"])})


def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig = request.headers.get("Stripe-Signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        print("WARNING: STRIPE_WEBHOOK_SECRET unset — rejecting webhook", flush=True)
        return ("webhook secret not configured", 503)
    try:
        ts = next((p.split("=", 1)[1] for p in sig.split(",") if p.startswith("t=")), "")
        sigs = [p.split("=", 1)[1] for p in sig.split(",") if p.startswith("v1=")]
        expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, s) for s in sigs):
            return ("invalid signature", 400)
    except Exception as e:
        print(f"stripe webhook signature error: {e}", flush=True)
        return ("signature error", 400)
    try:
        event = json.loads(payload)
    except Exception:
        return ("bad json", 400)
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    conn = db()
    if etype == "checkout.session.completed":
        ref, cust = obj.get("client_reference_id"), obj.get("customer")
        granted = False
        if ref:
            try:
                conn.execute("UPDATE users SET is_paid=1, stripe_customer_id=? WHERE id=?", (cust, int(ref)))
                conn.commit(); granted = True
            except (ValueError, TypeError):
                pass
        if not granted:
            email = ((obj.get("customer_details") or {}).get("email") or obj.get("customer_email") or "").strip().lower()
            if email:
                cur = conn.execute("UPDATE users SET is_paid=1, stripe_customer_id=? WHERE LOWER(email)=?", (cust, email))
                conn.commit()
                if not cur.rowcount:
                    print(f"stripe webhook: unmatched paid checkout (ref={ref!r} email={email!r})", flush=True)
    elif etype in ("customer.subscription.deleted", "invoice.payment_failed"):
        # Subscription product — these SHOULD revoke access (unlike a one-time purchase).
        cust = obj.get("customer")
        if cust:
            conn.execute("UPDATE users SET is_paid=0 WHERE stripe_customer_id=?", (cust,))
            conn.commit()
    return ("ok", 200)


def register(app):
    init_billing_tables()
    app.add_url_rule("/signup", "signup", signup, methods=["GET", "POST"])
    app.add_url_rule("/login", "login", login, methods=["GET", "POST"])
    app.add_url_rule("/logout", "logout", logout)
    app.add_url_rule("/upgrade", "upgrade", upgrade)
    app.add_url_rule("/upgrade/thanks", "upgrade_thanks", upgrade_thanks)
    app.add_url_rule("/api/account", "api_account", api_account)
    app.add_url_rule("/stripe/webhook", "stripe_webhook", stripe_webhook, methods=["POST"])
