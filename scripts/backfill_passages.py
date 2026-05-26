"""Backfill passage_div_html for tests that were scraped before the fix.

Handles all section structures:
  - English: <div id="mypassage">     (text)
  - Reading: <div class="mypassage">  (image scans of book pages)
  - Science: multiple <div class="mymessage"> blocks  (text + sometimes images)
  - Math:    no passage (each Q is standalone) → write empty string

Rewrites relative image URLs to absolute so they render when served locally.
Prioritizes English first (you're studying English right now), then others.
"""
import re
import sqlite3
import time
import requests
from bs4 import BeautifulSoup

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
BASE = "https://www.crackab.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 1.0

s = requests.Session()
s.headers.update({"User-Agent": UA})


def absolutize_imgs(html):
    """Rewrite relative /images/... to absolute crackab URLs."""
    return re.sub(r'src="(/[^"]+)"', lambda m: f'src="{BASE}{m.group(1)}"', html)


def extract_passage(html, section):
    """Pull the section-appropriate passage HTML. Returns string (may be empty)."""
    soup = BeautifulSoup(html, "html.parser")
    if section == "english":
        p = soup.find("div", id="mypassage")
        return absolutize_imgs(str(p)) if p else ""
    if section == "reading":
        p = soup.find("div", class_="mypassage")
        return absolutize_imgs(str(p)) if p else ""
    if section == "science":
        blocks = soup.find_all("div", class_="mymessage")
        if not blocks:
            return ""
        wrapped = '<div class="science-passages">' + "".join(str(b) for b in blocks) + "</div>"
        return absolutize_imgs(wrapped)
    if section == "math":
        return ""  # no passage; mark as scraped (empty) so we don't retry
    return ""


conn = sqlite3.connect(DB)
# Order: english first (id 301+), then reading (201+), science (401+), math last
rows = conn.execute("""
    SELECT id, section, url FROM tests
    WHERE passage_div_html IS NULL OR passage_div_html = ''
    ORDER BY CASE section
        WHEN 'english' THEN 1
        WHEN 'reading' THEN 2
        WHEN 'science' THEN 3
        WHEN 'math' THEN 4
        ELSE 9 END,
      id
""").fetchall()

print(f"{len(rows)} tests need passage backfill")
ok = 0
empty_ok = 0
for i, (tid, section, url) in enumerate(rows, 1):
    try:
        # Math doesn't need a fetch — just mark empty and move on (free, instant)
        if section == "math":
            conn.execute("UPDATE tests SET passage_div_html = ? WHERE id = ?", ("", tid))
            conn.commit()
            empty_ok += 1
            if i % 25 == 0:
                print(f"  [{i:>3}/{len(rows)}] test{tid} ({section}) → marked empty (running OK: {ok}, empty: {empty_ok})", flush=True)
            continue
        r = s.get(url, timeout=20)
        if r.status_code != 200:
            print(f"  [{i}/{len(rows)}] test{tid} → HTTP {r.status_code}", flush=True)
            continue
        passage = extract_passage(r.text, section)
        conn.execute("UPDATE tests SET passage_div_html = ? WHERE id = ?", (passage, tid))
        conn.commit()
        ok += 1
        if i % 10 == 0 or i == len(rows):
            print(f"  [{i:>3}/{len(rows)}] test{tid} ({section}) → {len(passage)} bytes (running OK: {ok})", flush=True)
        time.sleep(SLEEP)
    except Exception as e:
        print(f"  [{i}/{len(rows)}] test{tid} → ERROR {e}", flush=True)

print(f"DONE: {ok} fetched + {empty_ok} math-marked = {ok + empty_ok}/{len(rows)}")
conn.close()
