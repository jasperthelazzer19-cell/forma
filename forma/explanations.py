"""
Lazy explanation fetcher. Called by the Flask viewer.

URL pattern: /act/{section}/question-{global_q}-answer-and-explanation.html
Global Q number = (test_number - 1) * questions_per_test + q_num
"""
import re
import sqlite3
import time
import requests
from bs4 import BeautifulSoup

from forma.db import DB_PATH as DB
BASE = "https://www.crackab.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

_session = requests.Session()
_session.headers.update({"User-Agent": UA})


def sanitize_html(raw):
    """Strip dangerous tags/attributes from third-party (scraped) HTML while
    preserving the question/passage structure (forms, radio inputs, tables,
    images). Used on every passage/explanation blob before it's rendered with
    |safe / innerHTML, since the source content is not trusted."""
    if not raw:
        return raw
    soup = BeautifulSoup(raw, "html.parser")
    # Keep <form>/<input> — crackab passages embed the answer radios there.
    for tag in soup.find_all(["script", "style", "iframe", "object", "embed",
                              "link", "meta", "base"]):
        tag.decompose()
    for el in soup.find_all(True):
        for attr in list(el.attrs):
            val = el.attrs.get(attr)
            valstr = " ".join(val) if isinstance(val, list) else str(val or "")
            if attr.lower().startswith("on") or "javascript:" in valstr.lower():
                del el.attrs[attr]
    return str(soup)


def global_q_for(test_number, q_num, qs_per_test):
    return (test_number - 1) * qs_per_test + q_num


def fetch_explanation(section, global_q):
    """Fetch the explanation page, extract the explanation text. Return HTML string."""
    url = f"{BASE}/act/{section}/question-{global_q}-answer-and-explanation.html"
    try:
        r = _session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Find the main content block; explanation pages have a single article-like body
        main = soup.find("main") or soup.find("div", class_="content") or soup.body
        if not main:
            return None
        # Strip navigation lists (the "More ACT English Tests" sidebar)
        for ul in main.find_all("ul"):
            ul.decompose()
        for tag in main.find_all(["script", "style", "ins", "iframe", "object", "embed", "link", "meta", "form"]):
            tag.decompose()
        # Strip event-handler attributes and javascript: URLs — this HTML is
        # scraped from a third party and rendered with innerHTML, so it's an XSS
        # sink without this. (Not a full sanitizer, but closes the active vectors.)
        for el in main.find_all(True):
            for attr in list(el.attrs):
                val = el.attrs.get(attr)
                valstr = " ".join(val) if isinstance(val, list) else str(val or "")
                if attr.lower().startswith("on") or "javascript:" in valstr.lower():
                    del el.attrs[attr]
        # Strip the Previous/Next links
        for a in main.find_all("a"):
            if a.get_text(strip=True).lower() in ("previous", "next"):
                a.decompose()
        # Strip the test list anchors
        for a in main.find_all("a", href=re.compile(r"/act/[a-z]+/test\d+\.html")):
            a.decompose()
        html = str(main)
        # Tidy up runs of whitespace between tags
        html = re.sub(r">\s+<", "><", html)
        return html
    except Exception as e:
        return None


def get_explanation_cached(section, global_q):
    """Return (html, was_cached). Lazy-fetches and caches if missing."""
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("PRAGMA busy_timeout=8000")  # wait on locks instead of erroring under concurrent load
    row = conn.execute(
        "SELECT html_content FROM explanations WHERE section = ? AND global_q = ?",
        (section, global_q),
    ).fetchone()
    if row and row[0]:
        conn.close()
        return row[0], True
    html = fetch_explanation(section, global_q)
    if html:
        conn.execute(
            "INSERT OR REPLACE INTO explanations (section, global_q, html_content, fetched_at) VALUES (?,?,?,?)",
            (section, global_q, html, time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
    conn.close()
    return html, False
