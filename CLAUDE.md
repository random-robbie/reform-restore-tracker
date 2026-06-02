# Reform UK / Restore Britain Voting Tracker

## What this is
A tool that tracks every parliamentary vote by Reform UK (party ID 1036) and Restore Britain (party ID 1117) MPs, runs AI analysis on each division, and serves the data via a FastAPI web app.

## Stack
- **Data**: SQLite at `~/tools/reform/reform.db` (committed to git, deployed via Docker)
- **API**: FastAPI on port 8125 (`api.py`) — serves both JSON endpoints and HTML frontends
- **LLM**: Local vLLM at `http://192.168.1.231:8000/v1` running `minimax-m2.7` (reasoning model — always outputs `<think>...</think>` before JSON)
- **Hosting**: Render free tier (Docker), auto-deploys on every push to `main`
- **Scheduler**: macOS launchd plist at `~/Library/LaunchAgents/uk.parliament.reform-sync.plist` — runs `sync.sh` daily at 07:00

## Key files
| File | Purpose |
|------|---------|
| `db.py` | Schema init and `get_db()` context manager (WAL mode) |
| `parliament.py` | Parliament API client — MPs by party, vote pagination |
| `llm.py` | LLM analysis — strips `<think>` tags, extracts JSON, normalises impact fields |
| `fetch.py` | Orchestrates fetch (`--no-llm`) and analysis (`--analyse`) |
| `bills.py` | Links divisions to Parliament Bills API |
| `api.py` | FastAPI — all endpoints, HTML index `/`, votes browser `/votes` |
| `sync.sh` | Daily cron: fetch → analyse → bills → git commit + push |

## Parliament APIs
- Members: `https://members-api.parliament.uk/api/Members/Search?PartyId={id}&skip={n}&take=25`
- Votes: `https://commonsvotes-api.parliament.uk/data/divisions.json/membervoting?queryParameters.memberId={id}&queryParameters.skip={n}&queryParameters.take=25`
  - **Hard cap: 25 per page regardless of `take`** — always use `_PAGE = 25` and break when `len(data) < 25`
- Bills: `https://bills-api.parliament.uk/api/v1/Bills?searchTerm={name}&take=3`

## Public Parliament URLs
- Division: `https://votes.parliament.uk/Votes/Commons/Division/{id}`
- Bill: `https://bills.parliament.uk/bills/{id}`
- MP profile: `https://members.parliament.uk/member/{id}`
- MP votes: `https://members.parliament.uk/member/{id}/voting`

## LLM gotchas
- MiniMax M2.7 always starts with `<think>...</think>` — strip with `re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)`
- Use `max_tokens=8192` — think block alone is ~700 tokens
- System prompt must include: _"Think briefly. Output JSON only. No extra text."_ and _"Analyse votes purely from the bill title and result — you do not need external knowledge of the date. Always produce your analysis regardless of when the vote took place."_
- `guided_json` vLLM param doesn't enforce key names — use explicit JSON template in user message instead

## DB schema (key tables)
- `mps`: `member_id`, `name`, `party`, `constituency`, `thumbnail_url`
- `divisions`: `division_id`, `date`, `title`, `aye_count`, `no_count`, `plain_explanation`, `working_class_impact`, `working_class_reason`, `business_impact`, `business_reason`, `public_impact`, `impact_summary`, `analyzed`
- `mp_votes`: `member_id`, `division_id`, `voted_aye`, `voted_no`, `was_teller`
- `bills`: `bill_id`, `short_title`, `long_title`, `current_stage`, `is_act`, `is_defeated`, `last_update`
- `division_bills`: junction table linking divisions to bills

## Running locally
```bash
cd ~/tools/reform

# Fetch new votes (no LLM)
python3 fetch.py --no-llm

# Run LLM analysis on pending divisions (background)
nohup python3 fetch.py --analyse >> analysis.log 2>&1 &

# Sync bill links
python3 bills.py

# Start API
python3 -m uvicorn api:app --host 0.0.0.0 --port 8125 --reload
```

## Deployment
```bash
git add reform.db
git commit -m "sync: $(date '+%Y-%m-%d')"
git push origin main
# Render auto-deploys the Docker image — DB is baked in at build time
```

## API endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML index with live stats |
| `GET /votes` | HTML votes browser (search, filter, expandable cards) |
| `GET /api/mps` | All MPs with vote totals and last vote date |
| `GET /api/mps/activity` | Last vote date + time since for every MP |
| `GET /api/mps/{id}` | Single MP with vote summary |
| `GET /api/mps/{id}/recent` | Recent N votes for one MP |
| `GET /api/mps/all/recent` | Recent N votes for all MPs |
| `GET /api/mps/{id}/votes` | Full vote history with filters |
| `GET /api/divisions` | Paginated divisions with search/filter |
| `GET /api/divisions/latest` | Most recent divisions with MP votes |
| `GET /api/divisions/{id}` | Full division detail |
| `POST /api/divisions/{id}/analyse` | Re-run LLM on one division |
| `GET /api/bills` | All linked bills |
| `GET /api/bills/{id}` | Bill detail with divisions |
| `POST /api/bills/sync` | Re-sync from Parliament Bills API |
| `GET /api/search?q=` | Full-text search across divisions and bills |
| `GET /api/stats` | Totals, party breakdown, impact breakdown |
| `GET /api/sentiment/working-class?impact=hurts` | Divisions by working class impact |
| `GET /api/sentiment/business?impact=helps` | Divisions by business impact |
| `GET /api/sentiment/overview` | Cross-impact summary |

## Impact values
All impact fields use: `helps` / `hurts` / `neutral` / `mixed`
