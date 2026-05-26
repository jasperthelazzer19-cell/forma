"""
Download released-ACT PDFs from crackab.com/act-downloads/.

Discovers 400+ PDF download IDs on the index page, maps each ID → title,
filters to real released forms (skip test-prep books and EXPLORE/PLAN
PSAT-clone tests), downloads PDFs to official-pdfs/crackab/, and writes
a metadata index.
"""
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests

BASE = "https://www.crackab.com"
INDEX_URL = f"{BASE}/act-downloads/"
DOWNLOAD_URL = f"{BASE}/plus/download.php?open=0&aid={{aid}}&cid=3"
OUT_DIR = "/Users/jasperlasser/actprep-crackab/official-pdfs/crackab"
META_PATH = os.path.join(OUT_DIR, "_index.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 0.6  # be kind

os.makedirs(OUT_DIR, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent": UA})


def discover_ids():
    r = s.get(INDEX_URL, timeout=15)
    ids = sorted(set(int(m) for m in re.findall(r'/act-downloads/(\d+)\.html', r.text)))
    return ids


def discover_more_pages():
    """Index page might be paginated as /act-downloads/list_2.html etc."""
    r = s.get(INDEX_URL, timeout=15)
    pages = set(re.findall(r'/act-downloads/list[_-]?(\d+)\.html', r.text))
    return [int(p) for p in pages]


def map_titles(ids):
    """For each ID fetch the download page, extract title + actual PDF URL."""
    meta = {}
    for i, aid in enumerate(ids, 1):
        url = f"{BASE}/act-downloads/{aid}.html"
        try:
            r = s.get(url, timeout=12)
            title_m = re.search(r'<title>([^<]+)</title>', r.text)
            h1_m = re.search(r'<h1[^>]*>([^<]+)</h1>', r.text)
            # The "Download Link" anchor goes to /plus/download.php?aid=...
            dl_m = re.search(r'href="(/plus/download\.php\?[^"]*aid=' + str(aid) + r'[^"]*)"', r.text)
            meta[aid] = {
                "title": (title_m.group(1) if title_m else "").replace("_CrackAB.com", "").strip(),
                "h1": h1_m.group(1).strip() if h1_m else "",
                "download_php": dl_m.group(1) if dl_m else None,
            }
            if i % 30 == 0:
                print(f"  mapped {i}/{len(ids)}", flush=True)
        except Exception as e:
            print(f"  map err aid={aid}: {e}", flush=True)
        time.sleep(SLEEP)
    return meta


def is_real_act_form(title):
    """Filter: keep only real released full-length ACT tests."""
    t = (title or "").lower()
    if not t: return False
    if "real act" in t: return True
    if "full-length act" in t: return True
    # 16MC1 / 25MC5 / etc. — modern ACT codes
    if re.search(r'(form|act)\s+\d{1,2}mc\d', t): return True
    if "preparing for the act" in t: return True
    # Reject obvious non-forms
    bad = ("test prep book", "explore", "plan form", "english workbook",
           "math workbook", "reading workbook", "science workbook",
           "exam success", "study guide", "official guide",
           "premium", "strategy", "tutorial", "vocabulary")
    return not any(b in t for b in bad)


def resolve_pdf_url(aid, dl_php=None):
    """crackab download.php → testpapers.net ab.php → button onclick has PDF URL.

    Shortcut: hit testpapers.net/ab.php?id={aid} directly; it contains a button
    with onclick="location='...pdf'" pointing at the real file. The aid is the
    same identifier used by both crackab and testpapers.
    """
    try:
        r = s.get(f"https://b.testpapers.net/ab.php?id={aid}", timeout=15)
        if r.status_code != 200:
            return None
        m = re.search(r"location\s*=\s*['\"]([^'\"]+\.pdf)['\"]", r.text)
        if m:
            return m.group(1)
        # Fallback: any href ending in .pdf
        m = re.search(r'href="([^"]+\.pdf)"', r.text)
        if m:
            return m.group(1)
        return None
    except Exception as e:
        print(f"  resolve err aid={aid}: {e}", flush=True)
        return None


def download_pdf(aid, pdf_url, title):
    if not pdf_url: return None
    # Derive a clean filename from the title
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', title)[:60].strip('_')
    name = f"crackab-{aid:04d}-{slug}.pdf"
    path = os.path.join(OUT_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 50_000:
        return path  # already have it
    try:
        with s.get(pdf_url, timeout=60, stream=True) as r:
            if r.status_code != 200:
                print(f"  dl HTTP {r.status_code} for aid={aid}", flush=True)
                return None
            ctype = r.headers.get("Content-Type", "")
            if "html" in ctype:
                print(f"  dl returned HTML (not PDF) for aid={aid}", flush=True)
                return None
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        sz = os.path.getsize(path)
        if sz < 50_000:
            print(f"  dl too small ({sz}b) for aid={aid}, removing", flush=True)
            os.remove(path)
            return None
        return path
    except Exception as e:
        print(f"  dl err aid={aid}: {e}", flush=True)
        if os.path.exists(path): os.remove(path)
        return None


def main():
    print("=== STAGE 1: discover IDs ===", flush=True)
    ids = discover_ids()
    print(f"  {len(ids)} IDs on main index page", flush=True)
    # Quick map of ALL titles
    meta_path = os.path.join(OUT_DIR, "_titles.json")
    if os.path.exists(meta_path) and "--refresh" not in sys.argv:
        meta = json.load(open(meta_path))
        meta = {int(k): v for k, v in meta.items()}
        print(f"  loaded cached titles for {len(meta)} IDs", flush=True)
    else:
        print("=== STAGE 2: map titles (this hits 419 pages, ~5 min) ===", flush=True)
        meta = map_titles(ids)
        json.dump({str(k): v for k, v in meta.items()}, open(meta_path, "w"), indent=2)

    real = [(aid, m) for aid, m in meta.items() if is_real_act_form(m.get("title"))]
    print(f"\n=== STAGE 3: {len(real)} real ACT forms to download ===", flush=True)
    for aid, m in real[:5]:
        print(f"  e.g. {aid}: {m['title']}", flush=True)

    downloaded = []
    skipped = []
    for i, (aid, m) in enumerate(real, 1):
        pdf_url = resolve_pdf_url(aid, m.get("download_php"))
        if not pdf_url:
            skipped.append((aid, "no PDF URL"))
            time.sleep(SLEEP)
            continue
        path = download_pdf(aid, pdf_url, m["title"])
        if path:
            sz = os.path.getsize(path) // 1024
            downloaded.append((aid, path, sz))
            if i % 5 == 0 or i == len(real):
                print(f"  [{i:>3}/{len(real)}] aid={aid} → {sz}KB", flush=True)
        else:
            skipped.append((aid, "dl failed"))
        time.sleep(SLEEP)

    # Write final index
    out_idx = {
        "downloaded": [{"aid": aid, "path": p, "size_kb": sz, "title": meta[aid]["title"]}
                       for aid, p, sz in downloaded],
        "skipped": [{"aid": aid, "reason": r, "title": meta[aid]["title"]} for aid, r in skipped],
    }
    json.dump(out_idx, open(META_PATH, "w"), indent=2)
    print(f"\n=== DONE: {len(downloaded)} PDFs downloaded, {len(skipped)} skipped ===", flush=True)


if __name__ == "__main__":
    main()
