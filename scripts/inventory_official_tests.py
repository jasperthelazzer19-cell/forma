"""
Discover unique real official ACT released tests/forms inside crackab.com.

The /act/<section>/test<N>.html pages we already scraped are SECTION DRILLS
(15-Q chunks) — NOT full official tests. The real released ACT forms live
at /act-downloads/N.html with PDF links.

This script:
  1. Crawls /act-downloads/ (and its linked index pages)
  2. Fetches every /act-downloads/N.html
  3. Detects form codes (72C, A10, J08, F07, etc.) from title/URL/PDF filename
  4. Detects official-vs-third-party signals
  5. Tracks section + answer-key + explanation availability
  6. Deduplicates by form code / title / PDF filename
  7. Emits CSV + JSON + markdown report

Output files (in this dir):
  - official_act_test_inventory.csv
  - official_act_test_inventory.json
  - official_act_test_inventory.md
  - inventory.log (progress)

Polite ~1.2s/request. Skips re-fetches if downloads-raw-cache/<id>.html exists.
"""
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.crackab.com"
HERE = "/Users/jasperlasser/actprep-crackab"
CACHE = os.path.join(HERE, "downloads-raw-cache")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
SLEEP = 1.2

os.makedirs(CACHE, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent": UA})

# ── Form code patterns ────────────────────────────────────────────
# Standard ACT released-form codes are usually 2 digits + 1 letter (72C, 74F,
# 63E) or single letter + 2 digits (A10, F07, J08), or year + letter (2018D).
FORM_CODE_PATTERNS = [
    re.compile(r"\bForm\s+([A-Z]\d{1,3})\b"),
    re.compile(r"\bForm\s+(\d{2}[A-Z])\b"),
    re.compile(r"\b(\d{4}[A-Z])\b"),                  # 2018D
    re.compile(r"\b(\d{2}[A-Z]\d{2})\b"),             # 18MC4
    re.compile(r"\b([A-Z]\d{2})\b(?=\s*(?:test|form|act|pdf|\.))"),
    re.compile(r"\b(\d{2}[A-Z])\b(?=\s*(?:test|form|act|pdf|\.))"),
]
# Strong officialness signals in titles/URLs
OFFICIAL_TITLE_PATTERNS = re.compile(
    r"(official\s+act|released\s+act|act\s+form|preparing\s+for\s+the\s+act|"
    r"\btir\b|january\s+act|february\s+act|march\s+act|april\s+act|"
    r"may\s+act|june\s+act|july\s+act|august\s+act|september\s+act|"
    r"october\s+act|november\s+act|december\s+act|\d{4}\s+act\b)",
    re.I,
)
# Third-party / drill signals (NOT official)
THIRD_PARTY_PATTERNS = re.compile(
    r"(princeton\s+review|kaplan|barron|magoosh|crackab|practice\s+test\s+\d+|"
    r"drill|grammar|vocabulary|essay\s+sample|prep\s+book|"
    r"\d{2,3}\s+(?:english|math|reading|science)\s+practice|"
    r"sat\b)",
    re.I,
)
YEAR_PATTERN = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
SECTION_KEYWORDS = {
    "English":  re.compile(r"\benglish\b", re.I),
    "Math":     re.compile(r"\bmath(ematics)?\b", re.I),
    "Reading":  re.compile(r"\breading\b", re.I),
    "Science":  re.compile(r"\bscience\b", re.I),
    "Writing":  re.compile(r"\b(writing|essay)\b", re.I),
}

# ── Step 1: discover candidate /act-downloads/N.html links ────────
def discover_download_links():
    """Crawl /act-downloads/ and any sub-index pages, return set of full URLs."""
    seen = set()
    queue = [f"{BASE}/act-downloads/"]
    visited_indices = set()
    while queue:
        idx = queue.pop(0)
        if idx in visited_indices:
            continue
        visited_indices.add(idx)
        try:
            r = s.get(idx, timeout=20)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/act-downloads/\d+\.html$", href):
                    seen.add(urljoin(BASE, href))
                elif re.match(r"^/act-downloads/(page\d+|index\d+)?\.?html?$", href):
                    nxt = urljoin(BASE, href)
                    if nxt not in visited_indices:
                        queue.append(nxt)
            print(f"  index: {idx} → {len(seen)} download links total", flush=True)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  index {idx} ERROR: {e}", flush=True)
    return sorted(seen)


# ── Step 2: fetch each download page, extract structured metadata ─
def fetch_download(url):
    """Return raw HTML — cached locally so re-runs don't re-fetch."""
    name = os.path.basename(urlparse(url).path)
    cached = os.path.join(CACHE, name)
    if os.path.exists(cached) and os.path.getsize(cached) > 100:
        return open(cached).read()
    r = s.get(url, timeout=20)
    if r.status_code != 200:
        return None
    with open(cached, "w") as f:
        f.write(r.text)
    return r.text


def detect_form_codes(text):
    found = set()
    for p in FORM_CODE_PATTERNS:
        for m in p.findall(text or ""):
            found.add(m.upper())
    return sorted(found)


def parse_download(url, html):
    """Extract a candidate record. May return None if clearly not a test."""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
    # also collect h1/h2 + first big heading
    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        t = h.get_text(" ", strip=True)
        if t and len(t) < 250:
            headings.append(t)
    main_text = " ".join(headings + [title])

    # PDF links on the page
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            pdf_links.append(urljoin(BASE, href))

    # Form codes from title + headings + first PDF filename
    code_text = main_text + " " + " ".join(os.path.basename(p) for p in pdf_links)
    form_codes = detect_form_codes(code_text)

    # Officialness signals
    is_official_hit = bool(OFFICIAL_TITLE_PATTERNS.search(main_text))
    is_third_party_hit = bool(THIRD_PARTY_PATTERNS.search(main_text))

    # Year
    yr = YEAR_PATTERN.search(main_text)
    year = int(yr.group(1)) if yr else None

    # Section availability — search the page body for keywords
    body_text = soup.get_text(" ", strip=True).lower()
    sections = {k: bool(p.search(body_text)) for k, p in SECTION_KEYWORDS.items()}

    # Answer key / explanations availability
    has_answer_key = bool(
        re.search(r"answer\s*key|answers?\s+(?:to|for)", body_text)
        or any("answer" in os.path.basename(p).lower() for p in pdf_links)
    )
    has_explanations = bool(
        re.search(r"explanat(?:ion|ory)|worked\s+solutions|step[- ]by[- ]step", body_text)
        or any("explan" in os.path.basename(p).lower() for p in pdf_links)
    )

    # Confidence score 0-1
    conf = 0.0
    if form_codes:
        conf += 0.45
    if is_official_hit:
        conf += 0.35
    if year and 1989 <= year <= 2030:
        conf += 0.10
    if pdf_links:
        conf += 0.10
    if is_third_party_hit and not is_official_hit:
        conf -= 0.35
    if not main_text or len(main_text) < 8:
        conf -= 0.10
    conf = max(0.0, min(1.0, conf))

    # Skip pure-noise entries
    if not main_text and not pdf_links:
        return None

    return {
        "url": url,
        "title": title or (headings[0] if headings else ""),
        "headings": headings[:5],
        "form_codes": form_codes,
        "year": year,
        "pdf_urls": pdf_links,
        "sections": sections,
        "has_answer_key": has_answer_key,
        "has_explanations": has_explanations,
        "appears_official": is_official_hit and not is_third_party_hit,
        "appears_third_party": is_third_party_hit and not is_official_hit,
        "confidence": round(conf, 2),
    }


# ── Step 3: deduplicate ───────────────────────────────────────────
def title_key(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower())


def title_sim(a, b):
    return SequenceMatcher(None, title_key(a), title_key(b)).ratio()


def deduplicate(records):
    """Group by form_code (exact) and by title similarity (>= 0.85) and by
    shared PDF filename. Annotates each record with `duplicate_of` (canonical
    URL of the first record in its group)."""
    # Build index: form_code → list of URLs
    by_code = defaultdict(list)
    by_pdf = defaultdict(list)
    for r in records:
        for c in r["form_codes"]:
            by_code[c].append(r["url"])
        for p in r["pdf_urls"]:
            by_pdf[os.path.basename(p)].append(r["url"])

    # Canonical = the FIRST URL in any group (sorted)
    canonical = {}
    for group in list(by_code.values()) + list(by_pdf.values()):
        if len(group) < 2:
            continue
        canon = sorted(group)[0]
        for url in group:
            if url != canon:
                canonical[url] = canon

    # Title-similarity dup pass
    for i in range(len(records)):
        if records[i]["url"] in canonical:
            continue
        for j in range(i + 1, len(records)):
            if records[j]["url"] in canonical:
                continue
            if title_sim(records[i]["title"], records[j]["title"]) >= 0.85:
                canonical[records[j]["url"]] = records[i]["url"]

    for r in records:
        r["duplicate_of"] = canonical.get(r["url"])
    return records


# ── Step 4: emit outputs ───────────────────────────────────────────
def emit(records, out_dir=HERE):
    csv_path = os.path.join(out_dir, "official_act_test_inventory.csv")
    json_path = os.path.join(out_dir, "official_act_test_inventory.json")
    md_path = os.path.join(out_dir, "official_act_test_inventory.md")

    # CSV
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "url", "title", "form_codes", "year",
            "pdf_urls", "english", "math", "reading", "science", "writing",
            "has_answer_key", "has_explanations",
            "appears_official", "appears_third_party",
            "confidence", "duplicate_of",
        ])
        for r in records:
            w.writerow([
                r["url"], r["title"],
                "; ".join(r["form_codes"]),
                r.get("year") or "",
                "; ".join(r["pdf_urls"]),
                r["sections"]["English"], r["sections"]["Math"],
                r["sections"]["Reading"], r["sections"]["Science"],
                r["sections"]["Writing"],
                r["has_answer_key"], r["has_explanations"],
                r["appears_official"], r["appears_third_party"],
                r["confidence"], r.get("duplicate_of") or "",
            ])

    # JSON
    with open(json_path, "w") as f:
        json.dump(records, f, indent=2)

    # Markdown report
    n_total = len(records)
    n_unique = sum(1 for r in records if not r.get("duplicate_of"))
    n_official = sum(1 for r in records
                     if not r.get("duplicate_of") and r["appears_official"])
    questionable = [r for r in records
                    if not r.get("duplicate_of")
                    and 0.30 <= r["confidence"] < 0.60]
    duplicates = [r for r in records if r.get("duplicate_of")]
    top = sorted([r for r in records
                  if not r.get("duplicate_of") and r["appears_official"]
                  and r["pdf_urls"]],
                 key=lambda r: (-r["confidence"], r["title"]))[:25]
    with open(md_path, "w") as f:
        f.write("# Official ACT Test Inventory\n\n")
        f.write(f"_Generated from {n_total} crackab /act-downloads/ pages._\n\n")
        f.write("## Headline numbers\n\n")
        f.write(f"- **Unique candidates:** {n_unique}\n")
        f.write(f"- **Appears official:** {n_official}\n")
        f.write(f"- **Duplicates / recycled:** {len(duplicates)}\n")
        f.write(f"- **Questionable (need review):** {len(questionable)}\n\n")
        f.write("## Best PDFs to scrape first (top 25 by confidence)\n\n")
        f.write("| Confidence | Form codes | Year | Title | PDF |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for r in top:
            pdf = r["pdf_urls"][0] if r["pdf_urls"] else ""
            f.write(f"| {r['confidence']} | {', '.join(r['form_codes'])} | "
                    f"{r.get('year') or ''} | {r['title'][:80]} | "
                    f"[pdf]({pdf}) |\n")
        f.write("\n## Questionable (0.30–0.60 confidence)\n\n")
        for r in questionable[:50]:
            f.write(f"- [{r['title'][:90] or r['url']}]({r['url']})"
                    f" — codes={r['form_codes']} conf={r['confidence']}\n")
        f.write("\n## Duplicates / recycled\n\n")
        for r in duplicates[:80]:
            f.write(f"- {r['url']} → canonical: {r['duplicate_of']}\n")

    return csv_path, json_path, md_path


# ── Main ──────────────────────────────────────────────────────────
def main():
    print("=== STAGE 1: discovering download links ===", flush=True)
    links = discover_download_links()
    print(f"discovered {len(links)} unique /act-downloads/*.html URLs", flush=True)

    print("\n=== STAGE 2: fetching + parsing each ===", flush=True)
    records = []
    t0 = time.time()
    for i, url in enumerate(links, 1):
        try:
            html = fetch_download(url)
            if not html:
                continue
            rec = parse_download(url, html)
            if rec:
                records.append(rec)
            if i % 25 == 0 or i == len(links):
                elapsed = int(time.time() - t0)
                eta = int(elapsed / i * (len(links) - i)) if i else 0
                print(f"  [{i:>3}/{len(links)}] kept {len(records)} · "
                      f"{elapsed}s, ~{eta // 60}m{eta % 60}s left", flush=True)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  [{i}] {url} → ERROR {e}", flush=True)

    print("\n=== STAGE 3: deduplicating ===", flush=True)
    records = deduplicate(records)
    n_dup = sum(1 for r in records if r.get("duplicate_of"))
    print(f"  {n_dup} marked as duplicates", flush=True)

    print("\n=== STAGE 4: writing outputs ===", flush=True)
    csv_p, json_p, md_p = emit(records)
    print(f"  wrote {csv_p}", flush=True)
    print(f"  wrote {json_p}", flush=True)
    print(f"  wrote {md_p}", flush=True)
    print("\nDONE", flush=True)


if __name__ == "__main__":
    main()
