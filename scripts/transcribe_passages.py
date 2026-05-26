"""OCR every image in passage_div_html → store concatenated text in passage_text.

Uses macOS Vision framework via the local `ocr` Swift binary. Free, accurate,
~0.5s per image. Caches downloaded images so re-runs are cheap. Prioritizes
English first since that's what's being studied right now.
"""
import os
import re
import sqlite3
import subprocess
import time
from urllib.parse import urlparse, urljoin
import requests

DB = "/Users/jasperlasser/actprep-crackab/crackab.db"
HERE = "/Users/jasperlasser/actprep-crackab"
OCR_BIN = os.path.join(HERE, "ocr")
CACHE = os.path.join(HERE, "img-cache")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
BASE = "https://www.crackab.com"

os.makedirs(CACHE, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent": UA})


def img_path(url):
    name = os.path.basename(urlparse(url).path)
    return os.path.join(CACHE, name)


def fetch_image(url):
    path = img_path(url)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    r = s.get(url, timeout=30)
    if r.status_code != 200:
        return None
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def ocr_image(path):
    """Run OCR. Returns text or empty string if failed."""
    try:
        out = subprocess.run(
            [OCR_BIN, path],
            capture_output=True, text=True, timeout=20
        )
        return out.stdout.strip()
    except Exception as e:
        return ""


def transcribe_test(test_id, passage_html):
    """Find images in passage_html, OCR each, return concatenated text."""
    if not passage_html:
        return None
    raw_urls = re.findall(r'src="([^"]+\.(?:jpg|jpeg|png|gif))"', passage_html, re.I)
    urls = [u if u.startswith("http") else urljoin(BASE, u) for u in raw_urls]
    if not urls:
        # No images — use the text we already have (strip HTML tags)
        text = re.sub(r"<[^>]+>", "\n", passage_html)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text
    parts = []
    for url in urls:
        path = fetch_image(url)
        if not path:
            continue
        text = ocr_image(path)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def main():
    conn = sqlite3.connect(DB)
    # Process tests with non-empty passage_div_html and no passage_text yet.
    # English first.
    rows = conn.execute("""
        SELECT id, section, passage_div_html FROM tests
        WHERE (passage_text IS NULL OR passage_text = '')
          AND passage_div_html IS NOT NULL AND passage_div_html != ''
        ORDER BY CASE section
            WHEN 'english' THEN 1
            WHEN 'reading' THEN 2
            WHEN 'science' THEN 3
            ELSE 4 END,
          id
    """).fetchall()

    print(f"{len(rows)} tests to transcribe")
    ok = 0
    total_imgs = 0
    t0 = time.time()
    for i, (tid, section, html) in enumerate(rows, 1):
        try:
            txt = transcribe_test(tid, html)
            if txt:
                conn.execute("UPDATE tests SET passage_text = ? WHERE id = ?", (txt, tid))
                conn.commit()
                ok += 1
                n_imgs = len(re.findall(r'src="[^"]+\.(?:jpg|jpeg|png|gif)"', html, re.I))
                total_imgs += n_imgs
                elapsed = int(time.time() - t0)
                if i % 5 == 0 or i == len(rows):
                    eta = int(elapsed / i * (len(rows) - i)) if i else 0
                    print(f"  [{i:>3}/{len(rows)}] test{tid} ({section}) → {len(txt)} chars from {n_imgs} imgs · {elapsed}s elapsed, ~{eta//60}m{eta%60}s left", flush=True)
        except Exception as e:
            print(f"  [{i}/{len(rows)}] test{tid} → ERROR {e}", flush=True)

    print(f"DONE: {ok}/{len(rows)} transcribed · {total_imgs} total images OCRd")
    conn.close()


if __name__ == "__main__":
    main()
