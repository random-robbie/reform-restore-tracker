# Reform UK & Restore Britain — Voting Record Tracker

Track every parliamentary vote cast by **Reform UK** and **Restore Britain** MPs, with AI-generated plain-English explanations and impact analysis for working class people, businesses, and women & children.

---

## What it does

- Pulls every division voted on by tracked MPs from the [UK Parliament Commons Votes API](https://commonsvotes-api.parliament.uk)
- Links divisions to bills via the [Parliament Bills API](https://bills-api.parliament.uk)
- Runs each vote through a local LLM to generate:
  - Plain-English explanation of what was voted on
  - **Working class impact** — helps / hurts / neutral / mixed
  - **Business impact** — helps / hurts / neutral / mixed
  - **Women & children impact** — helps / hurts / neutral / mixed
  - Public impact summary
- Exposes a REST API and a searchable HTML frontend
- Commits the SQLite database to git daily and auto-deploys via [Render](https://render.com)

---

## MPs tracked

| Party | Parliament ID |
|-------|--------------|
| Reform UK | 1036 |
| Restore Britain | 1117 |

---

## Stack

| Component | Technology |
|-----------|-----------|
| Data store | SQLite (`reform.db`) |
| API | FastAPI + Uvicorn (port 8125) |
| LLM analysis | Local vLLM — MiniMax M2.7 |
| Scheduling | macOS launchd (daily at 07:00) |
| Hosting | Render free tier (Docker) |
| Deployment | git push → auto-deploy |

---

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML index with live stats |
| `GET /votes` | Searchable HTML votes browser |
| `GET /docs` | Swagger UI |
| `GET /api/mps` | All MPs with vote totals and last vote date |
| `GET /api/mps/activity` | Last vote date + time since for every MP |
| `GET /api/mps/{id}` | Single MP profile |
| `GET /api/mps/{id}/recent` | Recent N votes for one MP |
| `GET /api/mps/all/recent` | Recent N votes for every MP |
| `GET /api/mps/{id}/votes` | Full vote history with filters |
| `GET /api/divisions` | Paginated divisions — filter by `?q=` `?working_class_impact=` `?business_impact=` `?women_children_impact=` |
| `GET /api/divisions/latest` | Most recent divisions with MP votes |
| `GET /api/divisions/{id}` | Full division detail |
| `POST /api/divisions/{id}/analyse` | Re-run LLM on a single division |
| `GET /api/bills` | All linked bills |
| `GET /api/bills/{id}` | Bill detail with divisions |
| `GET /api/search?q=` | Full-text search across divisions and bills |
| `GET /api/stats` | Totals, party breakdown, impact breakdown |
| `GET /api/sentiment/working-class?impact=hurts` | Divisions by working class impact |
| `GET /api/sentiment/business?impact=helps` | Divisions by business impact |
| `GET /api/sentiment/women-children?impact=hurts` | Divisions by women & children impact |
| `GET /api/sentiment/overview` | Cross-impact summary |

---

## Running locally

### Prerequisites

- Python 3.11+
- A local vLLM instance running a compatible model (or adapt `llm.py` for any OpenAI-compatible API)

```bash
git clone <repo-url>
cd reform
pip install -r requirements.txt
```

### Fetch data

```bash
# Fetch all MPs and their full vote histories (no LLM)
python3 fetch.py --no-llm

# Run LLM analysis on unanalysed divisions (background)
nohup python3 fetch.py --analyse >> analysis.log 2>&1 &

# Back-fill women/children impact on already-analysed rows
nohup python3 fetch.py --patch >> patch.log 2>&1 &

# Sync bill links from Parliament Bills API
python3 bills.py
```

### Start the API

```bash
python3 -m uvicorn api:app --host 0.0.0.0 --port 8125 --reload
```

Then visit:
- `http://localhost:8125` — home page
- `http://localhost:8125/votes` — votes browser
- `http://localhost:8125/docs` — Swagger UI

---

## Database schema

```
mps             — member_id, name, party, constituency
divisions       — division_id, date, title, aye_count, no_count,
                  plain_explanation, working_class_impact, business_impact,
                  women_children_impact, public_impact, impact_summary, analyzed
mp_votes        — member_id, division_id, voted_aye, voted_no, was_teller
bills           — bill_id, short_title, long_title, current_stage, is_act
division_bills  — division_id ↔ bill_id (junction)
```

---

## Daily sync (macOS)

`sync.sh` runs the full pipeline: fetch → analyse → bills → git commit + push → Render redeploys.

The included launchd plist fires it at 07:00 daily:

```bash
cp uk.parliament.reform-sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/uk.parliament.reform-sync.plist
```

---

## Deploying to Render

1. Fork this repo
2. Create a new **Web Service** on [render.com](https://render.com), connected to your fork
3. Render detects `render.yaml` automatically — select **Docker** runtime, free plan
4. Every `git push origin main` triggers a new deploy with the latest database baked in

---

## Data sources

- [UK Parliament Commons Votes API](https://commonsvotes-api.parliament.uk)
- [UK Parliament Members API](https://members-api.parliament.uk)
- [UK Parliament Bills API](https://bills-api.parliament.uk)

All data is public domain under the [Open Parliament Licence](https://www.parliament.uk/site-information/copyright-parliament/open-parliament-licence/).
