# Forma

ACT prep, methodically. Every official ACT question, indexed and drilled.

- **17,218** real ACT questions
- **147** released official forms
- **102** topics tagged for adaptive drilling
- AI tutor that explains every wrong answer

## Run locally

```bash
pip install -r requirements.txt
python3 app.py            # localhost:5574
```

## Layout

```
forma/
  __init__.py         package marker
  shell.py            colors, fonts, HEAD, sidebar, palette, section labels
  db.py               SQLite helpers + first-boot seeding
  landing.py          public landing pages (/v1…/v5)
  explanations.py     legacy crackab.com explanation fetcher
app.py                entrypoint — home, sections, test viewer, official forms
features.py           dashboard, review, adaptive, full-test, search, topics, bookmarks, /api/*
data/
  crackab.db          17K questions across 703 tests (147 official ACT forms)
scripts/              one-shot ETL: scrape, OCR, parse, import, generate, tag, transcribe
archive/              backups and large source PDFs (gitignored)
logs/                 runtime logs (gitignored)
```

## Routes

- `/` — today / home dashboard
- `/section/<sec>` — section drilling (english / math / reading / science)
- `/test/<id>` — single test viewer
- `/dashboard` — stats, score predictor, weakest topics
- `/review` — wrong-answer review queue
- `/adaptive` — adaptive drill targeting your weakest topics
- `/full-test` — full-length timed simulation
- `/official` — every released official ACT form
- `/topics` — drill by topic across all sections
- `/search` — full-text search across all questions
- `/bookmarks` — saved questions
- `/v5` — public landing page

## Deploy

Railway. `Procfile` runs `gunicorn app:app`. `DATABASE_PATH` env var should
point to a persistent volume so progress survives redeploys.

## Stack

- Flask (single-process, SQLite-backed)
- Anthropic Claude for the AI tutor (`/api/tutor`)
- Switzer (Fontshare) + JetBrains Mono (Google Fonts)
- Vanilla JS, no build step

## Built by

Jasper. 2026.
