# Job AI Agent

An intelligent job search assistant that matches your CV against job postings using AI. Scrapes listings from [DOU.ua](https://jobs.dou.ua), parses your CV, and ranks jobs based on your qualifications.

## Features

- **CV Parsing** — upload your CV and extract structured information (title, experience, skills)
- **Job Scraping** — Chrome extension scrapes DOU.ua listings automatically
- **AI Matching** — ranks jobs by relevance using Jaccard similarity + OpenAI analysis
- **AI Enrichment** — enriches job postings with structured data via OpenAI (GPT-4o-mini)
- **Caching** — avoids duplicate OpenAI calls; reuses recent scrape results
- **User Accounts** — optional registration with saved search history

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite |
| AI | OpenAI API (CV parsing, matching, enrichment) |
| Scraping | Selenium, BeautifulSoup, httpx |
| Frontend | Vanilla JS, HTML/CSS |
| Extension | Chrome Extension (Manifest V3) |

## Project Structure

```
job-ai-agent/
├── server/
│   ├── fast_api.py          # FastAPI app & all API endpoints
│   ├── scraper.py           # Selenium scraper for DOU.ua
│   └── jobs_sync.py         # Upsert jobs into DB
├── backend/
│   ├── ai/
│   │   ├── cv_parser.py     # CV text → structured data (heuristic / OpenAI)
│   │   ├── cv_classifier.py # Detect DOU category from CV
│   │   ├── enricher.py      # Fetch job page text + OpenAI enrichment
│   │   └── matcher.py       # Score & rank jobs against CV
│   └── db/
│       └── database.py      # SQLAlchemy models & DB init
├── client/
│   ├── index.html           # Single-page web UI
│   ├── app.js               # UI logic (step flow, API calls)
│   └── styles.css
├── chrome_extension/
│   ├── manifest.json
│   ├── content.js           # Collects jobs from DOU page
│   └── popup.js             # Extension popup UI
├── protocol/
│   ├── python/job.py        # Shared data structures (Python)
│   └── js/job.ts            # Shared data structures (TypeScript)
├── tests/
│   ├── test_api.py
│   ├── test_match.py
│   └── test_cv_plugin_target.py
├── conftest.py
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env   # add your OPENAI_API_KEY

# 3. Start the server
uvicorn server.fast_api:app --host 0.0.0.0 --port 8000 --reload

# 4. Open in browser
open http://localhost:8000
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Register user |
| POST | `/api/auth/login` | Login user |
| POST | `/api/cv/run` | Upload CV + scrape jobs (main flow) |
| GET | `/api/jobs` | List jobs for current run |
| POST | `/api/jobs/sync` | Sync jobs from Chrome extension |
| POST | `/api/jobs/fetch-text-all` | Download full job descriptions |
| POST | `/api/jobs/enrich-all` | Enrich jobs with OpenAI |
| GET | `/api/match/scores` | CV–job match scores |
| GET | `/api/match/report` | Full match report |
| GET | `/api/match/job/{id}/analysis` | Detailed single-job analysis |
| GET | `/api/history/runs` | Search history |

Interactive docs: `http://localhost:8000/docs`

## Environment Variables

```env
OPENAI_API_KEY=sk-...
OPENAI_CV_PARSER=1            # 0 = heuristic, 1 = OpenAI
OPENAI_CV_CLASSIFIER=1
OPENAI_MATCHER=1
REUSE_RUN_MAX_AGE_HOURS=4     # Skip re-scraping if recent run exists
DB_URL=sqlite:///jobs_search.db
CHROME_BINARY=/usr/bin/google-chrome
```

## Running Tests

```bash
pytest tests/ -v
```

## Chrome Extension

1. Run `./build-extension.sh`
2. Load `chrome_extension/` as an unpacked extension in Chrome
3. Navigate to [jobs.dou.ua](https://jobs.dou.ua) and click the extension icon

## License

MIT
