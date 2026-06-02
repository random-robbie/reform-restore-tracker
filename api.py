#!/usr/bin/env python3
"""
Reform UK / Restore Britain voting record API.

Start: uvicorn api:app --host 0.0.0.0 --port 8125 --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from db import get_db, DB_PATH
from datetime import date as _date
import os

app = FastAPI(
    title="Reform UK Voting Record API",
    description="Search and explore how Reform UK and Restore Britain MPs have voted, with plain-English AI analysis.",
    version="1.1.0",
)


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _row(row) -> dict:
    return dict(row) if row else {}


# Parliament public URLs — generated from IDs we already have
def _div_url(division_id: int) -> str:
    return f"https://votes.parliament.uk/Votes/Commons/Division/{division_id}"

def _bill_url(bill_id: int) -> str:
    return f"https://bills.parliament.uk/bills/{bill_id}"

def _mp_url(member_id: int) -> str:
    return f"https://members.parliament.uk/member/{member_id}"

def _mp_votes_url(member_id: int) -> str:
    return f"https://members.parliament.uk/member/{member_id}/voting"


def _time_since(date_str: str | None) -> str:
    if not date_str:
        return "unknown"
    try:
        then = _date.fromisoformat(date_str[:10])
    except ValueError:
        return "unknown"
    days = (_date.today() - then).days
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "1 week ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def _enrich_division(d: dict) -> dict:
    d["parliament_url"] = _div_url(d["division_id"])
    if d.get("bill_id"):
        d["bill_url"] = _bill_url(d["bill_id"])
    return d


def _enrich_mp(m: dict) -> dict:
    m["parliament_url"]       = _mp_url(m["member_id"])
    m["parliament_votes_url"] = _mp_votes_url(m["member_id"])
    return m


# ---------------------------------------------------------------------------
# Index page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    with get_db() as conn:
        mps        = conn.execute("SELECT COUNT(*) FROM mps").fetchone()[0]
        divisions  = conn.execute("SELECT COUNT(*) FROM divisions").fetchone()[0]
        votes      = conn.execute("SELECT COUNT(*) FROM mp_votes").fetchone()[0]
        analysed   = conn.execute("SELECT COUNT(*) FROM divisions WHERE analyzed=1").fetchone()[0]
        bills      = conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0]

    pct = round(analysed / divisions * 100) if divisions else 0
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reform UK Voting Record API</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }}
    a {{ color: #60a5fa; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
              padding: 2.5rem 2rem; border-bottom: 1px solid #4338ca; }}
    header h1 {{ font-size: 1.9rem; font-weight: 700; color: #fff; }}
    header p  {{ margin-top: .5rem; color: #a5b4fc; font-size: 1rem; max-width: 620px; }}

    .badge {{ display: inline-block; padding: .2rem .65rem; border-radius: 9999px;
              font-size: .72rem; font-weight: 600; margin-left: .4rem; vertical-align: middle; }}
    .badge-blue   {{ background: #1e40af; color: #bfdbfe; }}
    .badge-green  {{ background: #166534; color: #bbf7d0; }}
    .badge-purple {{ background: #5b21b6; color: #ddd6fe; }}

    .stats {{ display: flex; flex-wrap: wrap; gap: 1rem; padding: 1.5rem 2rem;
              background: #161b27; border-bottom: 1px solid #1e293b; }}
    .stat {{ background: #1e293b; border-radius: .5rem; padding: .9rem 1.4rem; flex: 1; min-width: 120px; }}
    .stat-num {{ font-size: 1.7rem; font-weight: 700; color: #60a5fa; }}
    .stat-lbl {{ font-size: .75rem; color: #94a3b8; margin-top: .2rem; text-transform: uppercase; letter-spacing: .05em; }}

    main {{ max-width: 960px; margin: 0 auto; padding: 2rem; }}

    .cta {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem; }}
    .btn {{ display: inline-flex; align-items: center; gap: .4rem; padding: .65rem 1.3rem;
            border-radius: .4rem; font-size: .9rem; font-weight: 600; cursor: pointer; }}
    .btn-primary {{ background: #4f46e5; color: #fff; }}
    .btn-primary:hover {{ background: #4338ca; text-decoration: none; }}
    .btn-secondary {{ background: #1e293b; color: #e2e8f0; border: 1px solid #334155; }}
    .btn-secondary:hover {{ background: #273449; text-decoration: none; }}

    h2 {{ font-size: 1.1rem; font-weight: 600; color: #94a3b8; text-transform: uppercase;
          letter-spacing: .08em; margin: 2rem 0 .8rem; }}

    .endpoints {{ display: flex; flex-direction: column; gap: .5rem; }}
    .ep {{ background: #1e293b; border: 1px solid #334155; border-radius: .5rem;
           padding: .75rem 1rem; display: flex; align-items: baseline; gap: .75rem; flex-wrap: wrap; }}
    .ep:hover {{ border-color: #4f46e5; }}
    .method {{ font-size: .72rem; font-weight: 700; padding: .15rem .5rem; border-radius: .25rem;
               font-family: monospace; white-space: nowrap; }}
    .get  {{ background: #1e3a5f; color: #7dd3fc; }}
    .post {{ background: #1a3328; color: #6ee7b7; }}
    .path {{ font-family: monospace; font-size: .88rem; color: #c4b5fd; flex-shrink: 0; }}
    .desc {{ font-size: .85rem; color: #94a3b8; flex: 1; }}

    .group-label {{ font-size: .7rem; font-weight: 700; text-transform: uppercase;
                    letter-spacing: .1em; color: #475569; margin-top: 1.2rem; margin-bottom: .3rem; }}

    footer {{ text-align: center; padding: 2rem; color: #475569; font-size: .8rem;
              border-top: 1px solid #1e293b; margin-top: 3rem; }}
  </style>
</head>
<body>

<header>
  <h1>Reform UK &amp; Restore Britain — Voting Record API</h1>
  <p>Track every parliamentary vote by Reform UK and Restore Britain MPs, with AI-generated plain-English explanations and working class / business impact analysis.</p>
</header>

<div class="stats">
  <div class="stat"><div class="stat-num">{mps}</div><div class="stat-lbl">MPs tracked</div></div>
  <div class="stat"><div class="stat-num">{divisions:,}</div><div class="stat-lbl">Divisions</div></div>
  <div class="stat"><div class="stat-num">{votes:,}</div><div class="stat-lbl">Vote records</div></div>
  <div class="stat"><div class="stat-num">{bills}</div><div class="stat-lbl">Bills linked</div></div>
  <div class="stat"><div class="stat-num">{analysed:,}<span style="font-size:1rem;color:#94a3b8"> / {pct}%</span></div><div class="stat-lbl">AI analysed</div></div>
</div>

<main>
  <div class="cta">
    <a class="btn btn-primary" href="/docs">📖 Swagger UI</a>
    <a class="btn btn-secondary" href="/redoc">ReDoc</a>
    <a class="btn btn-secondary" href="/api/stats">Live stats JSON</a>
    <a class="btn btn-secondary" href="/api/divisions/latest">Latest votes</a>
  </div>

  <h2>MPs</h2>
  <div class="endpoints">
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/mps">/api/mps</a><span class="desc">List all tracked MPs with vote totals. Filter with <code>?party=Reform UK</code></span></div>
    <div class="ep"><span class="method get">GET</span><span class="path">/api/mps/{{id}}</span><span class="desc">Single MP profile with aye/no summary</span></div>
    <div class="ep"><span class="method get">GET</span><span class="path">/api/mps/{{id}}/recent</span><span class="desc">Most recent votes for one MP <span class="badge badge-blue">?limit=10</span></span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/mps/all/recent">/api/mps/all/recent</a><span class="desc">Latest N votes for every MP in one response</span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/mps/activity">/api/mps/activity</a><span class="desc">Last vote date and time since last vote for every tracked MP, sorted by most recent</span></div>
    <div class="ep"><span class="method get">GET</span><span class="path">/api/mps/{{id}}/votes</span><span class="desc">Full vote history with filters: <code>?voted=aye|no|abstain</code> <code>?working_class_impact=hurts</code> <code>?q=search</code></span></div>
  </div>

  <h2>Divisions (Votes)</h2>
  <div class="endpoints">
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/divisions/latest">/api/divisions/latest</a><span class="desc">Most recent divisions with each MP's vote and linked bill <span class="badge badge-blue">?limit=20</span></span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/divisions">/api/divisions</a><span class="desc">Paginated list. Filter by <code>?q=</code> <code>?from_date=</code> <code>?working_class_impact=</code> <code>?bill_id=</code></span></div>
    <div class="ep"><span class="method get">GET</span><span class="path">/api/divisions/{{id}}</span><span class="desc">Full division detail: AI analysis, MP votes, linked bill</span></div>
    <div class="ep"><span class="method post">POST</span><span class="path">/api/divisions/{{id}}/analyse</span><span class="desc">Re-run AI analysis on a single division using the local LLM</span></div>
  </div>

  <h2>Bills</h2>
  <div class="endpoints">
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/bills">/api/bills</a><span class="desc">All bills voted on by tracked MPs. Filter with <code>?q=</code> <code>?is_act=true</code></span></div>
    <div class="ep"><span class="method get">GET</span><span class="path">/api/bills/{{id}}</span><span class="desc">Bill detail with every linked division and MP votes</span></div>
    <div class="ep"><span class="method post">POST</span><span class="path">/api/bills/sync</span><span class="desc">Re-sync bill data from the Parliament Bills API</span></div>
  </div>

  <h2>Sentiment &amp; Impact</h2>
  <div class="endpoints">
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/sentiment/overview">/api/sentiment/overview</a><span class="desc">Cross-impact summary — most harmful and most beneficial divisions for working class and business</span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/sentiment/working-class?impact=hurts">/api/sentiment/working-class</a><span class="desc">Divisions filtered by working class impact <span class="badge badge-purple">?impact=helps|hurts|neutral|mixed</span></span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/sentiment/business?impact=helps">/api/sentiment/business</a><span class="desc">Divisions filtered by business impact <span class="badge badge-purple">?impact=helps|hurts|neutral|mixed</span></span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/sentiment/women-children?impact=hurts">/api/sentiment/women-children</a><span class="desc">Divisions filtered by women &amp; children impact <span class="badge badge-purple">?impact=helps|hurts|neutral|mixed</span></span></div>
  </div>

  <h2>Search &amp; Stats</h2>
  <div class="endpoints">
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/search?q=NHS">/api/search</a><span class="desc">Full-text search across division titles, AI explanations, bills. Returns divisions + bills</span></div>
    <div class="ep"><span class="method get">GET</span><a class="path" href="/api/stats">/api/stats</a><span class="desc">Totals, party breakdown, impact breakdowns, most-voted divisions</span></div>
  </div>
</main>

<footer>
  Data sourced from the UK Parliament Commons Votes API and Parliament Bills API &bull;
  AI analysis by MiniMax M2.7 running locally &bull;
  <a href="/docs">Swagger UI</a> &bull;
  <a href="/votes">Votes Browser</a>
</footer>

</body>
</html>""")


# ---------------------------------------------------------------------------
# Votes browser (HTML frontend)
# ---------------------------------------------------------------------------

@app.get("/votes", response_class=HTMLResponse, include_in_schema=False)
def votes_browser():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reform UK — Votes Browser</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg:      #0f1117;
      --surface: #1e293b;
      --border:  #334155;
      --text:    #e2e8f0;
      --muted:   #94a3b8;
      --accent:  #6366f1;
      --green:   #16a34a;
      --red:     #dc2626;
      --yellow:  #d97706;
      --blue:    #2563eb;
    }
    body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
    a { color: #60a5fa; text-decoration: none; }
    a:hover { text-decoration: underline; }
    button { cursor: pointer; font-family: inherit; }

    /* ── Header ── */
    header { background: linear-gradient(135deg,#1e1b4b,#312e81); padding: 1.4rem 1.5rem;
             border-bottom: 1px solid #4338ca; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem; }
    header h1 { font-size: 1.25rem; font-weight: 700; color: #fff; }
    header nav a { font-size: .85rem; color: #a5b4fc; margin-left: 1rem; }

    /* ── Controls ── */
    .controls { padding: 1rem 1.5rem; background: #161b27; border-bottom: 1px solid var(--border);
                display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; }
    .search-wrap { position: relative; flex: 1; min-width: 220px; }
    .search-wrap input { width: 100%; padding: .55rem .9rem .55rem 2.4rem; background: var(--surface);
                         border: 1px solid var(--border); border-radius: .4rem; color: var(--text);
                         font-size: .9rem; outline: none; }
    .search-wrap input:focus { border-color: var(--accent); }
    .search-wrap .ico { position: absolute; left: .7rem; top: 50%; transform: translateY(-50%);
                        color: var(--muted); font-size: .9rem; pointer-events: none; }
    .filters { display: flex; flex-wrap: wrap; gap: .4rem; }
    .chip { padding: .35rem .8rem; border-radius: 9999px; border: 1px solid var(--border);
            background: var(--surface); color: var(--muted); font-size: .78rem; font-weight: 500; transition: all .15s; }
    .chip:hover { border-color: var(--accent); color: var(--text); }
    .chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
    .sort-select { padding: .5rem .8rem; background: var(--surface); border: 1px solid var(--border);
                   border-radius: .4rem; color: var(--text); font-size: .82rem; outline: none; }

    /* ── Grid ── */
    .grid { display: flex; flex-direction: column; gap: 0; }

    /* ── Card ── */
    .card { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.1rem 1.5rem; }
    .card:hover { background: #243049; }
    .card-header { display: flex; align-items: flex-start; gap: .75rem; cursor: pointer; }
    .card-meta { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin-bottom: .4rem; }
    .date-badge { font-size: .72rem; color: var(--muted); }
    .result-badge { font-size: .7rem; font-weight: 700; padding: .1rem .5rem; border-radius: .25rem; }
    .passed { background: #14532d; color: #86efac; }
    .failed { background: #450a0a; color: #fca5a5; }
    .bill-tag { font-size: .7rem; background: #1e3a5f; color: #7dd3fc; padding: .1rem .5rem; border-radius: .25rem; }

    .card-title { font-size: .97rem; font-weight: 600; color: var(--text); line-height: 1.35; flex: 1; }
    .vote-bar-wrap { min-width: 110px; text-align: right; }
    .vote-counts { font-size: .78rem; color: var(--muted); display: flex; gap: .5rem; justify-content: flex-end; margin-bottom: .3rem; }
    .aye-n { color: #4ade80; font-weight: 600; }
    .no-n  { color: #f87171; font-weight: 600; }
    .bar { height: 5px; border-radius: 9999px; background: #1e3a2f; overflow: hidden; width: 110px; }
    .bar-fill { height: 100%; background: #4ade80; border-radius: 9999px; transition: width .3s; }

    /* ── Expand ── */
    .card-body { display: none; margin-top: .9rem; padding-top: .9rem; border-top: 1px solid var(--border); }
    .card-body.open { display: block; }

    .explanation { font-size: .88rem; color: var(--muted); line-height: 1.6; margin-bottom: .9rem; }

    .impact-grid { display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: .9rem; }
    .impact-box { flex: 1; min-width: 180px; background: #0f1117; border: 1px solid var(--border);
                  border-radius: .4rem; padding: .7rem .9rem; }
    .impact-box h4 { font-size: .7rem; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin-bottom: .3rem; }
    .impact-box .impact-val { font-size: .88rem; font-weight: 700; margin-bottom: .25rem; }
    .impact-box .impact-reason { font-size: .8rem; color: var(--muted); line-height: 1.4; }

    .impact-helps  { color: #4ade80; }
    .impact-hurts  { color: #f87171; }
    .impact-mixed  { color: #fbbf24; }
    .impact-neutral { color: var(--muted); }

    .public-impact { font-size: .83rem; color: var(--muted); line-height: 1.6;
                     background: #0f1117; border-radius: .4rem; padding: .7rem .9rem;
                     border: 1px solid var(--border); margin-bottom: .9rem; }
    .public-impact h4 { font-size: .7rem; text-transform: uppercase; letter-spacing: .07em;
                        color: var(--muted); margin-bottom: .3rem; }

    .summary-pill { display: inline-block; background: #1e293b; border: 1px solid var(--border);
                    border-radius: 9999px; padding: .3rem .8rem; font-size: .8rem;
                    color: var(--text); margin-bottom: .9rem; }

    .mp-votes { margin-top: .6rem; }
    .mp-votes h4 { font-size: .7rem; text-transform: uppercase; letter-spacing: .07em;
                   color: var(--muted); margin-bottom: .5rem; }
    .mp-list { display: flex; flex-wrap: wrap; gap: .4rem; }
    .mp-tag { font-size: .75rem; padding: .2rem .6rem; border-radius: .25rem; font-weight: 500; }
    .mp-aye { background: #14532d; color: #86efac; }
    .mp-no  { background: #450a0a; color: #fca5a5; }
    .mp-abs { background: #1c1917; color: var(--muted); }

    .ext-links { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: .9rem; }
    .ext-link { display: inline-flex; align-items: center; gap: .35rem; font-size: .78rem;
                padding: .3rem .75rem; border-radius: .3rem; border: 1px solid var(--border);
                background: #0f1117; color: #60a5fa; transition: border-color .15s; }
    .ext-link:hover { border-color: #60a5fa; text-decoration: none; }
    .mp-tag a { color: inherit; text-decoration: none; }
    .mp-tag a:hover { text-decoration: underline; }

    .not-analysed { font-size: .83rem; color: var(--muted); font-style: italic; padding: .4rem 0; }

    /* ── Pagination ── */
    .pagination { display: flex; justify-content: center; align-items: center;
                  gap: .5rem; padding: 1.5rem; flex-wrap: wrap; }
    .page-btn { padding: .45rem .9rem; background: var(--surface); border: 1px solid var(--border);
                border-radius: .35rem; color: var(--text); font-size: .85rem; }
    .page-btn:hover { border-color: var(--accent); }
    .page-btn.active { background: var(--accent); border-color: var(--accent); }
    .page-btn:disabled { opacity: .4; cursor: not-allowed; }
    .page-info { font-size: .82rem; color: var(--muted); }

    /* ── Loading / empty ── */
    .loading { text-align: center; padding: 3rem; color: var(--muted); font-size: .95rem; }
    .spinner { display: inline-block; width: 24px; height: 24px; border: 3px solid var(--border);
               border-top-color: var(--accent); border-radius: 50%;
               animation: spin .7s linear infinite; margin-right: .5rem; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .empty { text-align: center; padding: 3rem; color: var(--muted); }

    .impact-chips { display: flex; flex-wrap: wrap; gap: .3rem; }
  </style>
</head>
<body>

<header>
  <h1>⚖️ Reform UK &amp; Restore Britain — Votes Browser</h1>
  <nav>
    <a href="/">Home</a>
    <a href="/docs">API Docs</a>
  </nav>
</header>

<div class="controls">
  <div class="search-wrap">
    <span class="ico">🔍</span>
    <input id="search" type="text" placeholder="Search votes, bills, topics…" autocomplete="off">
  </div>

  <div class="filters">
    <span style="font-size:.75rem;color:var(--muted);align-self:center">Working class:</span>
    <button class="chip active" data-wc="">All</button>
    <button class="chip" data-wc="helps">✅ Helps</button>
    <button class="chip" data-wc="hurts">❌ Hurts</button>
    <button class="chip" data-wc="mixed">⚠️ Mixed</button>
    <button class="chip" data-wc="neutral">➖ Neutral</button>
  </div>

  <div class="filters">
    <span style="font-size:.75rem;color:var(--muted);align-self:center">Business:</span>
    <button class="chip active" data-biz="">All</button>
    <button class="chip" data-biz="helps">✅ Helps</button>
    <button class="chip" data-biz="hurts">❌ Hurts</button>
    <button class="chip" data-biz="mixed">⚠️ Mixed</button>
    <button class="chip" data-biz="neutral">➖ Neutral</button>
  </div>

  <div class="filters">
    <span style="font-size:.75rem;color:var(--muted);align-self:center">Women &amp; children:</span>
    <button class="chip active" data-wch="">All</button>
    <button class="chip" data-wch="helps">✅ Protects</button>
    <button class="chip" data-wch="hurts">❌ Harms</button>
    <button class="chip" data-wch="mixed">⚠️ Mixed</button>
    <button class="chip" data-wch="neutral">➖ Neutral</button>
  </div>

  <select class="sort-select" id="sort">
    <option value="recent">Most recent</option>
    <option value="analysed">AI analysed first</option>
  </select>
</div>

<div id="grid" class="grid">
  <div class="loading"><span class="spinner"></span>Loading votes…</div>
</div>

<div id="pagination" class="pagination"></div>

<script>
const PAGE = 25;
let skip = 0, total = 0;
let searchTimer = null;
let activeWC = '', activeBiz = '', activeWCh = '';

// ── Fetch & render ──────────────────────────────────────────────────────────
async function load() {
  const q   = document.getElementById('search').value.trim();
  const sort = document.getElementById('sort').value;

  const params = new URLSearchParams({
    limit: PAGE,
    skip,
    ...(q          && { q }),
    ...(activeWC   && { working_class_impact: activeWC }),
    ...(activeBiz  && { business_impact: activeBiz }),
    ...(activeWCh  && { women_children_impact: activeWCh }),
  });

  document.getElementById('grid').innerHTML =
    '<div class="loading"><span class="spinner"></span>Loading…</div>';

  try {
    const r = await fetch('/api/divisions?' + params);
    const data = await r.json();
    total = data.total;
    renderCards(data.divisions);
    renderPagination();
  } catch(e) {
    document.getElementById('grid').innerHTML =
      '<div class="empty">⚠️ Could not load data. Is the API running?</div>';
  }
}

// ── Card rendering ───────────────────────────────────────────────────────────
function impactClass(v) {
  return v ? 'impact-' + v : 'impact-neutral';
}
function impactLabel(v) {
  return { helps:'Helps ✅', hurts:'Hurts ❌', mixed:'Mixed ⚠️', neutral:'Neutral ➖' }[v] || '—';
}
function passed(d) { return d.aye_count > d.no_count; }

function renderCards(divs) {
  if (!divs.length) {
    document.getElementById('grid').innerHTML =
      '<div class="empty">No votes found matching your filters.</div>';
    return;
  }
  document.getElementById('grid').innerHTML = divs.map(d => {
    const total_votes = (d.aye_count || 0) + (d.no_count || 0);
    const ayePct = total_votes ? Math.round(d.aye_count / total_votes * 100) : 0;
    const result = passed(d);

    const billTag = d.bill_short_title
      ? `<a class="bill-tag" href="${d.bill_url || '#'}" target="_blank" rel="noopener"
            title="View bill on Parliament website" onclick="event.stopPropagation()">
           📄 ${esc(d.bill_short_title)} ↗
         </a>` : '';

    let body = '';
    if (d.analyzed) {
      body = `
        <div class="card-body" id="body-${d.division_id}">
          <p class="explanation">${esc(d.plain_explanation || '')}</p>
          <div class="impact-grid">
            <div class="impact-box">
              <h4>Working class impact</h4>
              <div class="impact-val ${impactClass(d.working_class_impact)}">${impactLabel(d.working_class_impact)}</div>
              <div class="impact-reason">${esc(d.working_class_reason || '')}</div>
            </div>
            <div class="impact-box">
              <h4>Business impact</h4>
              <div class="impact-val ${impactClass(d.business_impact)}">${impactLabel(d.business_impact)}</div>
              <div class="impact-reason">${esc(d.business_reason || '')}</div>
            </div>
            <div class="impact-box">
              <h4>Women &amp; children</h4>
              <div class="impact-val ${impactClass(d.women_children_impact)}">${impactLabel(d.women_children_impact)}</div>
              <div class="impact-reason">${esc(d.women_children_reason || '')}</div>
            </div>
          </div>
          ${d.public_impact ? `
          <div class="public-impact">
            <h4>Public impact</h4>
            ${esc(d.public_impact)}
          </div>` : ''}
          ${d.impact_summary ? `<div class="summary-pill">💡 ${esc(d.impact_summary)}</div>` : ''}
          <div class="ext-links">
            <a class="ext-link" href="https://votes.parliament.uk/Votes/Commons/Division/${d.division_id}" target="_blank" rel="noopener">🗳️ Full vote record ↗</a>
            ${d.bill_url ? `<a class="ext-link" href="${d.bill_url}" target="_blank" rel="noopener">📋 View bill on Parliament ↗</a>` : ''}
          </div>
          <div class="mp-votes"><h4>Reform / Restore MPs voted</h4><div class="mp-list"></div></div>
        </div>`;
    } else {
      body = `<div class="card-body" id="body-${d.division_id}">
        <p class="not-analysed">AI analysis pending for this division.</p>
      </div>`;
    }

    return `
    <div class="card" id="card-${d.division_id}">
      <div class="card-header" onclick="toggle(${d.division_id})">
        <div style="flex:1">
          <div class="card-meta">
            <span class="date-badge">${d.date || ''}</span>
            <span class="result-badge ${result ? 'passed' : 'failed'}">${result ? 'PASSED' : 'FAILED'}</span>
            ${billTag}
            ${d.analyzed ? '<span class="bill-tag" style="background:#1e3a1e;color:#86efac">✓ AI analysed</span>' : ''}
          </div>
          <div class="card-title">${esc(d.title)}</div>
        </div>
        <div class="vote-bar-wrap">
          <div class="vote-counts">
            <span class="aye-n">Aye ${d.aye_count || 0}</span>
            <span class="no-n">No ${d.no_count || 0}</span>
          </div>
          <div class="bar"><div class="bar-fill" style="width:${ayePct}%"></div></div>
        </div>
      </div>
      ${body}
    </div>`;
  }).join('');
}

async function toggle(id) {
  const body = document.getElementById('body-' + id);
  if (!body) return;
  const opening = !body.classList.contains('open');
  body.classList.toggle('open');
  // Lazy-load MP votes on first open
  if (opening && !body.dataset.loaded) {
    body.dataset.loaded = '1';
    const mpList = body.querySelector('.mp-list');
    if (mpList && mpList.innerHTML.trim() === '') {
      try {
        const r = await fetch('/api/divisions/' + id);
        const d = await r.json();
        const votes = (d.mp_votes || []).map(v => {
          const voteLabel = v.voted_aye ? 'Aye' : v.voted_no ? 'No' : 'Abstain';
          const cls = v.voted_aye ? 'mp-aye' : v.voted_no ? 'mp-no' : 'mp-abs';
          const profileUrl = v.parliament_url || `https://members.parliament.uk/member/${v.member_id}`;
          const votingUrl  = v.parliament_votes_url || `https://members.parliament.uk/member/${v.member_id}/voting`;
          return `<span class="mp-tag ${cls}" title="${esc(v.constituency || '')}">
            <a href="${profileUrl}" target="_blank" rel="noopener" title="MP profile">${esc(v.name)}</a>
            ${voteLabel}
            <a href="${votingUrl}" target="_blank" rel="noopener" title="Full voting record" style="opacity:.7;font-size:.7rem">⧉</a>
          </span>`;
        }).join('');
        mpList.innerHTML = votes || '<span style="color:var(--muted);font-size:.8rem">No tracked MP voted on this</span>';
      } catch(e) { /* ignore */ }
    }
  }
}

// ── Pagination ────────────────────────────────────────────────────────────────
function renderPagination() {
  const pages = Math.ceil(total / PAGE);
  const cur   = Math.floor(skip / PAGE);
  const el    = document.getElementById('pagination');

  if (pages <= 1) { el.innerHTML = ''; return; }

  let html = `<span class="page-info">${total.toLocaleString()} votes</span>`;
  html += `<button class="page-btn" onclick="goPage(${cur-1})" ${cur===0?'disabled':''}>← Prev</button>`;

  const start = Math.max(0, cur - 2), end = Math.min(pages - 1, cur + 2);
  if (start > 0) html += `<button class="page-btn" onclick="goPage(0)">1</button>${start>1?'<span style="color:var(--muted)">…</span>':''}`;
  for (let i = start; i <= end; i++)
    html += `<button class="page-btn ${i===cur?'active':''}" onclick="goPage(${i})">${i+1}</button>`;
  if (end < pages-1) html += `${end<pages-2?'<span style="color:var(--muted)">…</span>':''}<button class="page-btn" onclick="goPage(${pages-1})">${pages}</button>`;

  html += `<button class="page-btn" onclick="goPage(${cur+1})" ${cur>=pages-1?'disabled':''}>Next →</button>`;
  el.innerHTML = html;
}

function goPage(p) { skip = p * PAGE; load(); window.scrollTo(0,0); }

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Event wiring ──────────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { skip = 0; load(); }, 400);
});

document.getElementById('sort').addEventListener('change', () => { skip = 0; load(); });

// Working class filter chips
document.querySelectorAll('[data-wc]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-wc]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeWC = btn.dataset.wc;
    skip = 0; load();
  });
});

// Business filter chips
document.querySelectorAll('[data-biz]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-biz]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeBiz = btn.dataset.biz;
    skip = 0; load();
  });
});

// Women & children filter chips
document.querySelectorAll('[data-wch]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-wch]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeWCh = btn.dataset.wch;
    skip = 0; load();
  });
});

// ── Boot ──────────────────────────────────────────────────────────────────────
load();
</script>
</body>
</html>""")


# ---------------------------------------------------------------------------
# MPs
# ---------------------------------------------------------------------------

@app.get("/api/mps/activity", summary="Last vote date and time since for every MP", tags=["MPs"])
def mps_activity():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT m.member_id, m.name, m.party, m.constituency,
                   MAX(d.date) AS last_vote_date,
                   COUNT(v.division_id) AS total_votes,
                   SUM(v.voted_aye) AS aye_votes,
                   SUM(v.voted_no) AS no_votes
            FROM mps m
            LEFT JOIN mp_votes v USING(member_id)
            LEFT JOIN divisions d USING(division_id)
            GROUP BY m.member_id
            ORDER BY last_vote_date DESC NULLS LAST
        """).fetchall()
    result = []
    for r in rows:
        mp = _enrich_mp(dict(r))
        mp["last_vote_time_since"] = _time_since(mp.get("last_vote_date"))
        result.append(mp)
    return result


@app.get("/api/mps", summary="List all tracked MPs", tags=["MPs"])
def list_mps(
    party: str | None = Query(None, description="Filter: 'Reform UK' or 'Restore Britain'"),
):
    with get_db() as conn:
        sql = "SELECT * FROM mps WHERE party = ? ORDER BY name" if party else "SELECT * FROM mps ORDER BY party, name"
        params = [party] if party else []
        result = []
        for r in conn.execute(sql, params).fetchall():
            mp = _enrich_mp(dict(r))
            stats = _row(conn.execute("""
                SELECT COUNT(*) AS total_votes, SUM(voted_aye) AS aye_votes, SUM(voted_no) AS no_votes,
                       MAX(d.date) AS last_vote_date
                FROM mp_votes v JOIN divisions d USING(division_id)
                WHERE v.member_id = ?
            """, (mp["member_id"],)).fetchone())
            stats["last_vote_time_since"] = _time_since(stats.get("last_vote_date"))
            mp["vote_stats"] = stats
            result.append(mp)
    return result


@app.get("/api/mps/{member_id}", summary="Single MP with vote summary", tags=["MPs"])
def get_mp(member_id: int):
    with get_db() as conn:
        mp = _row(conn.execute("SELECT * FROM mps WHERE member_id = ?", (member_id,)).fetchone())
        if not mp:
            raise HTTPException(404, "MP not found")
        mp = _enrich_mp(mp)
        stats = _row(conn.execute("""
            SELECT COUNT(*) AS total_votes, SUM(voted_aye) AS aye_votes, SUM(voted_no) AS no_votes,
                   MAX(d.date) AS last_vote_date
            FROM mp_votes v JOIN divisions d USING(division_id)
            WHERE v.member_id = ?
        """, (member_id,)).fetchone())
        stats["last_vote_time_since"] = _time_since(stats.get("last_vote_date"))
        mp["vote_stats"] = stats
    return mp


@app.get("/api/mps/{member_id}/votes", summary="All votes for an MP", tags=["MPs"])
def get_mp_votes(
    member_id: int,
    skip:  int  = Query(0,   ge=0),
    limit: int  = Query(50,  ge=1, le=200),
    q:     str | None = Query(None, description="Search division title"),
    voted: str | None = Query(None, description="aye | no | abstain"),
    working_class_impact: str | None = Query(None, description="helps | hurts | neutral | mixed"),
    business_impact:      str | None = Query(None, description="helps | hurts | neutral | mixed"),
):
    with get_db() as conn:
        mp = conn.execute("SELECT name FROM mps WHERE member_id = ?", (member_id,)).fetchone()
        if not mp:
            raise HTTPException(404, "MP not found")

        filters = ["v.member_id = ?"]
        params  = [member_id]
        if q:
            filters.append("d.title LIKE ?"); params.append(f"%{q}%")
        if voted == "aye":
            filters.append("v.voted_aye = 1")
        elif voted == "no":
            filters.append("v.voted_no = 1")
        elif voted == "abstain":
            filters.append("v.voted_aye = 0 AND v.voted_no = 0")
        if working_class_impact:
            filters.append("d.working_class_impact = ?"); params.append(working_class_impact)
        if business_impact:
            filters.append("d.business_impact = ?"); params.append(business_impact)

        where = " AND ".join(filters)
        total = conn.execute(
            f"SELECT COUNT(*) FROM mp_votes v JOIN divisions d USING(division_id) WHERE {where}", params
        ).fetchone()[0]

        rows = conn.execute(f"""
            SELECT v.voted_aye, v.voted_no, v.was_teller,
                   d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.working_class_reason,
                   d.business_impact,   d.business_reason, d.public_impact, d.impact_summary,
                   d.analyzed,
                   b.bill_id, b.short_title AS bill_short_title, b.current_stage AS bill_stage
            FROM mp_votes v
            JOIN divisions d USING(division_id)
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE {where}
            ORDER BY d.date DESC
            LIMIT ? OFFSET ?
        """, params + [limit, skip]).fetchall()

        return {"mp": mp["name"], "total": total, "skip": skip, "limit": limit,
                "votes": _rows(rows)}


# ---------------------------------------------------------------------------
# Divisions
# ---------------------------------------------------------------------------

@app.get("/api/divisions", summary="List / search divisions", tags=["Divisions"])
def list_divisions(
    q:     str | None = Query(None, description="Search title or AI explanation"),
    from_date: str | None = Query(None, description="YYYY-MM-DD"),
    to_date:   str | None = Query(None, description="YYYY-MM-DD"),
    working_class_impact:  str | None = Query(None),
    business_impact:       str | None = Query(None),
    women_children_impact: str | None = Query(None),
    bill_id: int | None = Query(None, description="Filter to a specific bill"),
    skip:  int = Query(0,  ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    filters, params = [], []
    if q:
        filters.append("(d.title LIKE ? OR d.plain_explanation LIKE ? OR d.impact_summary LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if from_date:
        filters.append("d.date >= ?"); params.append(from_date)
    if to_date:
        filters.append("d.date <= ?"); params.append(to_date)
    if working_class_impact:
        filters.append("d.working_class_impact = ?"); params.append(working_class_impact)
    if business_impact:
        filters.append("d.business_impact = ?"); params.append(business_impact)
    if women_children_impact:
        filters.append("d.women_children_impact = ?"); params.append(women_children_impact)
    if bill_id:
        filters.append("db.bill_id = ?"); params.append(bill_id)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    join  = "LEFT JOIN division_bills db ON db.division_id = d.division_id" if bill_id else ""

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(DISTINCT d.division_id) FROM divisions d {join} {where}", params
        ).fetchone()[0]
        rows = conn.execute(f"""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.business_impact,
                   d.women_children_impact, d.impact_summary, d.analyzed,
                   b.bill_id, b.short_title AS bill_short_title, b.current_stage AS bill_stage
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            {where}
            ORDER BY d.date DESC
            LIMIT ? OFFSET ?
        """, params + [limit, skip]).fetchall()

    return {"total": total, "skip": skip, "limit": limit,
            "divisions": [_enrich_division(d) for d in _rows(rows)]}


@app.get("/api/divisions/latest", summary="Most recent divisions with MP votes", tags=["Divisions"])
def latest_divisions(
    limit: int = Query(20, ge=1, le=100),
):
    with get_db() as conn:
        divs = conn.execute("""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.working_class_reason,
                   d.business_impact,   d.business_reason, d.public_impact, d.impact_summary,
                   d.analyzed,
                   b.bill_id, b.short_title AS bill_short_title,
                   b.long_title AS bill_long_title, b.current_stage AS bill_stage,
                   b.is_act, b.is_defeated
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            ORDER BY d.date DESC, d.division_id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        result = []
        for div in divs:
            d = _enrich_division(dict(div))
            votes = conn.execute("""
                SELECT m.member_id, m.name, m.party, m.constituency,
                       v.voted_aye, v.voted_no, v.was_teller
                FROM mp_votes v JOIN mps m USING(member_id)
                WHERE v.division_id = ?
                ORDER BY m.party, m.name
            """, (d["division_id"],)).fetchall()
            d["mp_votes"] = [_enrich_mp(dict(v)) for v in votes]
            result.append(d)
    return result


@app.get("/api/divisions/{division_id}", summary="Full division detail with MP votes", tags=["Divisions"])
def get_division(division_id: int):
    with get_db() as conn:
        div = _row(conn.execute("SELECT * FROM divisions WHERE division_id = ?", (division_id,)).fetchone())
        if not div:
            raise HTTPException(404, "Division not found")

        # Attach linked bill
        bill = _row(conn.execute("""
            SELECT b.* FROM bills b
            JOIN division_bills db ON db.bill_id = b.bill_id
            WHERE db.division_id = ?
        """, (division_id,)).fetchone())
        if bill:
            bill["parliament_url"] = _bill_url(bill["bill_id"])
        div["bill"] = bill or None

        div["mp_votes"] = [_enrich_mp(dict(v)) for v in conn.execute("""
            SELECT m.member_id, m.name, m.party, m.constituency,
                   v.voted_aye, v.voted_no, v.was_teller
            FROM mp_votes v JOIN mps m USING(member_id)
            WHERE v.division_id = ?
            ORDER BY m.party, m.name
        """, (division_id,)).fetchall()]
        _enrich_division(div)
    return div


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

@app.get("/api/bills", summary="List bills voted on by tracked MPs", tags=["Bills"])
def list_bills(
    q:     str | None = Query(None, description="Search bill title"),
    is_act: bool | None = Query(None, description="Filter to Acts only"),
    skip:  int = Query(0,  ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    filters, params = [], []
    if q:
        filters.append("(b.short_title LIKE ? OR b.long_title LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if is_act is not None:
        filters.append("b.is_act = ?"); params.append(1 if is_act else 0)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM bills b {where}", params).fetchone()[0]
        rows  = conn.execute(f"""
            SELECT b.*,
                   COUNT(DISTINCT db.division_id) AS division_count
            FROM bills b
            LEFT JOIN division_bills db ON db.bill_id = b.bill_id
            {where}
            GROUP BY b.bill_id
            ORDER BY b.last_update DESC, b.bill_id DESC
            LIMIT ? OFFSET ?
        """, params + [limit, skip]).fetchall()
    bills_out = []
    for b in _rows(rows):
        b["parliament_url"] = _bill_url(b["bill_id"])
        bills_out.append(b)
    return {"total": total, "skip": skip, "limit": limit, "bills": bills_out}


@app.get("/api/bills/{bill_id}", summary="Bill detail with all linked divisions", tags=["Bills"])
def get_bill(bill_id: int):
    with get_db() as conn:
        bill = _row(conn.execute("SELECT * FROM bills WHERE bill_id = ?", (bill_id,)).fetchone())
        if not bill:
            raise HTTPException(404, "Bill not found")
        bill["parliament_url"] = _bill_url(bill_id)

        divs = conn.execute("""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.business_impact,
                   d.impact_summary, d.analyzed
            FROM divisions d
            JOIN division_bills db ON db.division_id = d.division_id
            WHERE db.bill_id = ?
            ORDER BY d.date DESC
        """, (bill_id,)).fetchall()

        result = []
        for div in divs:
            d = _enrich_division(dict(div))
            d["mp_votes"] = [_enrich_mp(dict(v)) for v in conn.execute("""
                SELECT m.member_id, m.name, m.party, v.voted_aye, v.voted_no
                FROM mp_votes v JOIN mps m USING(member_id)
                WHERE v.division_id = ?
                ORDER BY m.name
            """, (d["division_id"],)).fetchall()]
            result.append(d)

        bill["divisions"] = result
    return bill


@app.post("/api/bills/sync", summary="Sync bill data from Parliament Bills API", tags=["Bills"])
def sync_bills_endpoint():
    from bills import sync_bills
    try:
        n = sync_bills(verbose=False)
        return {"status": "ok", "linked": n}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/api/search", summary="Search divisions and bills", tags=["Search"])
def search(
    q:     str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
):
    with get_db() as conn:
        divs = conn.execute("""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.business_impact,
                   d.impact_summary, d.analyzed,
                   b.bill_id, b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.title LIKE ? OR d.plain_explanation LIKE ?
               OR d.public_impact LIKE ? OR d.impact_summary LIKE ?
            ORDER BY d.date DESC
            LIMIT ?
        """, [f"%{q}%"] * 4 + [limit]).fetchall()

        bills = conn.execute("""
            SELECT b.bill_id, b.short_title, b.long_title, b.current_stage,
                   b.is_act, b.is_defeated,
                   COUNT(DISTINCT db.division_id) AS division_count
            FROM bills b
            LEFT JOIN division_bills db ON db.bill_id = b.bill_id
            WHERE b.short_title LIKE ? OR b.long_title LIKE ?
            GROUP BY b.bill_id
            ORDER BY b.last_update DESC
            LIMIT ?
        """, [f"%{q}%", f"%{q}%", max(5, limit // 4)]).fetchall()

    return {"query": q, "divisions": _rows(divs), "bills": _rows(bills)}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats", summary="Overall stats", tags=["Stats"])
def stats():
    with get_db() as conn:
        totals = {
            "mps":                conn.execute("SELECT COUNT(*) FROM mps").fetchone()[0],
            "divisions":          conn.execute("SELECT COUNT(*) FROM divisions").fetchone()[0],
            "votes_recorded":     conn.execute("SELECT COUNT(*) FROM mp_votes").fetchone()[0],
            "divisions_analysed": conn.execute("SELECT COUNT(*) FROM divisions WHERE analyzed=1").fetchone()[0],
            "bills_linked":       conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0],
        }
        return {
            "totals": totals,
            "by_party": _rows(conn.execute("""
                SELECT m.party, COUNT(DISTINCT v.member_id) AS mps,
                       COUNT(*) AS total_votes, SUM(v.voted_aye) AS ayes, SUM(v.voted_no) AS noes
                FROM mp_votes v JOIN mps m USING(member_id) GROUP BY m.party
            """).fetchall()),
            "working_class_impact": _rows(conn.execute("""
                SELECT working_class_impact, COUNT(*) AS count FROM divisions
                WHERE analyzed=1 GROUP BY working_class_impact ORDER BY count DESC
            """).fetchall()),
            "business_impact": _rows(conn.execute("""
                SELECT business_impact, COUNT(*) AS count FROM divisions
                WHERE analyzed=1 GROUP BY business_impact ORDER BY count DESC
            """).fetchall()),
            "most_voted_divisions": _rows(conn.execute("""
                SELECT d.division_id, d.date, d.title, d.impact_summary, COUNT(*) AS reform_votes
                FROM mp_votes v JOIN divisions d USING(division_id)
                GROUP BY d.division_id ORDER BY reform_votes DESC LIMIT 10
            """).fetchall()),
        }


# ---------------------------------------------------------------------------
# Re-analyse a single division
# ---------------------------------------------------------------------------

@app.post("/api/divisions/{division_id}/analyse", summary="Re-run LLM analysis on a division", tags=["Divisions"])
def reanalyse_division(division_id: int):
    from llm import analyse_division as llm_analyse
    with get_db() as conn:
        div = _row(conn.execute("SELECT * FROM divisions WHERE division_id = ?", (division_id,)).fetchone())
    if not div:
        raise HTTPException(404, "Division not found")
    try:
        result = llm_analyse(div["title"], div["date"] or "", div["aye_count"] or 0, div["no_count"] or 0)
        with get_db() as conn:
            conn.execute("""
                UPDATE divisions SET plain_explanation=:plain_explanation,
                    working_class_impact=:working_class_impact, working_class_reason=:working_class_reason,
                    business_impact=:business_impact, business_reason=:business_reason,
                    public_impact=:public_impact, impact_summary=:impact_summary, analyzed=1
                WHERE division_id=:did
            """, {**result, "did": division_id})
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Per-MP recent votes
# ---------------------------------------------------------------------------

@app.get("/api/mps/{member_id}/recent", summary="10 most recent votes for an MP", tags=["MPs"])
def get_mp_recent(member_id: int, limit: int = Query(10, ge=1, le=50)):
    with get_db() as conn:
        mp = conn.execute("SELECT * FROM mps WHERE member_id = ?", (member_id,)).fetchone()
        if not mp:
            raise HTTPException(404, "MP not found")
        rows = conn.execute("""
            SELECT v.voted_aye, v.voted_no, v.was_teller,
                   d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.business_impact,
                   d.impact_summary, d.analyzed,
                   b.bill_id, b.short_title AS bill_short_title, b.current_stage AS bill_stage
            FROM mp_votes v
            JOIN divisions d USING(division_id)
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE v.member_id = ?
            ORDER BY d.date DESC, d.division_id DESC
            LIMIT ?
        """, (member_id, limit)).fetchall()
    return {"mp": dict(mp), "recent_votes": _rows(rows)}


@app.get("/api/mps/all/recent", summary="Most recent N votes for every MP", tags=["MPs"])
def all_mps_recent(limit: int = Query(10, ge=1, le=50)):
    with get_db() as conn:
        mps = conn.execute("SELECT * FROM mps ORDER BY party, name").fetchall()
        result = []
        for mp in mps:
            mid = mp["member_id"]
            rows = conn.execute("""
                SELECT v.voted_aye, v.voted_no,
                       d.division_id, d.date, d.title, d.aye_count, d.no_count,
                       d.plain_explanation, d.working_class_impact, d.business_impact,
                       d.impact_summary, d.analyzed,
                       b.short_title AS bill_short_title
                FROM mp_votes v
                JOIN divisions d USING(division_id)
                LEFT JOIN division_bills db ON db.division_id = d.division_id
                LEFT JOIN bills b ON b.bill_id = db.bill_id
                WHERE v.member_id = ?
                ORDER BY d.date DESC, d.division_id DESC
                LIMIT ?
            """, (mid, limit)).fetchall()
            result.append({
                "member_id":    mid,
                "name":         mp["name"],
                "party":        mp["party"],
                "constituency": mp["constituency"],
                "recent_votes": _rows(rows),
            })
    return result


# ---------------------------------------------------------------------------
# Sentiment / impact endpoints
# ---------------------------------------------------------------------------

@app.get("/api/sentiment/working-class", summary="Divisions by working class impact", tags=["Sentiment"])
def working_class_sentiment(
    impact: str = Query(..., description="helps | hurts | neutral | mixed"),
    skip:   int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
):
    valid = {"helps", "hurts", "neutral", "mixed"}
    if impact not in valid:
        raise HTTPException(400, f"impact must be one of: {', '.join(sorted(valid))}")

    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM divisions WHERE working_class_impact = ?", (impact,)
        ).fetchone()[0]
        rows = conn.execute("""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.working_class_impact, d.working_class_reason,
                   d.business_impact, d.impact_summary,
                   b.bill_id, b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.working_class_impact = ?
            ORDER BY d.date DESC
            LIMIT ? OFFSET ?
        """, (impact, limit, skip)).fetchall()

        # Attach MP votes for each division
        result = []
        for row in rows:
            d = dict(row)
            d["mp_votes"] = _rows(conn.execute("""
                SELECT m.name, m.party, v.voted_aye, v.voted_no
                FROM mp_votes v JOIN mps m USING(member_id)
                WHERE v.division_id = ?
                ORDER BY m.name
            """, (d["division_id"],)).fetchall())
            result.append(d)

    return {
        "impact": impact,
        "label": {
            "helps":   "Pro working class",
            "hurts":   "Anti working class",
            "neutral": "Neutral for working class",
            "mixed":   "Mixed for working class",
        }[impact],
        "total": total, "skip": skip, "limit": limit,
        "divisions": result,
    }


@app.get("/api/sentiment/business", summary="Divisions by business impact", tags=["Sentiment"])
def business_sentiment(
    impact: str = Query(..., description="helps | hurts | neutral | mixed"),
    skip:   int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
):
    valid = {"helps", "hurts", "neutral", "mixed"}
    if impact not in valid:
        raise HTTPException(400, f"impact must be one of: {', '.join(sorted(valid))}")

    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM divisions WHERE business_impact = ?", (impact,)
        ).fetchone()[0]
        rows = conn.execute("""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.business_impact, d.business_reason,
                   d.working_class_impact, d.impact_summary,
                   b.bill_id, b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.business_impact = ?
            ORDER BY d.date DESC
            LIMIT ? OFFSET ?
        """, (impact, limit, skip)).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            d["mp_votes"] = _rows(conn.execute("""
                SELECT m.name, m.party, v.voted_aye, v.voted_no
                FROM mp_votes v JOIN mps m USING(member_id)
                WHERE v.division_id = ?
                ORDER BY m.name
            """, (d["division_id"],)).fetchall())
            result.append(d)

    return {
        "impact": impact,
        "label": {
            "helps":   "Pro business",
            "hurts":   "Anti business",
            "neutral": "Neutral for business",
            "mixed":   "Mixed for business",
        }[impact],
        "total": total, "skip": skip, "limit": limit,
        "divisions": result,
    }


@app.get("/api/sentiment/women-children", summary="Divisions by women and children impact", tags=["Sentiment"])
def women_children_sentiment(
    impact: str = Query(..., description="helps | hurts | neutral | mixed"),
    skip:   int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
):
    valid = {"helps", "hurts", "neutral", "mixed"}
    if impact not in valid:
        raise HTTPException(400, f"impact must be one of: {', '.join(sorted(valid))}")

    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM divisions WHERE women_children_impact = ?", (impact,)
        ).fetchone()[0]
        rows = conn.execute("""
            SELECT d.division_id, d.date, d.title, d.aye_count, d.no_count,
                   d.plain_explanation, d.women_children_impact, d.women_children_reason,
                   d.working_class_impact, d.business_impact, d.impact_summary,
                   b.bill_id, b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.women_children_impact = ?
            ORDER BY d.date DESC
            LIMIT ? OFFSET ?
        """, (impact, limit, skip)).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            d["mp_votes"] = _rows(conn.execute("""
                SELECT m.name, m.party, v.voted_aye, v.voted_no
                FROM mp_votes v JOIN mps m USING(member_id)
                WHERE v.division_id = ?
                ORDER BY m.name
            """, (d["division_id"],)).fetchall())
            result.append(d)

    return {
        "impact": impact,
        "label": {
            "helps":   "Protects / benefits women and children",
            "hurts":   "Harms / fails to protect women and children",
            "neutral": "Neutral for women and children",
            "mixed":   "Mixed for women and children",
        }[impact],
        "total": total, "skip": skip, "limit": limit,
        "divisions": result,
    }


@app.get("/api/sentiment/overview", summary="Cross-impact summary (working class vs business)", tags=["Sentiment"])
def sentiment_overview():
    with get_db() as conn:
        wc = _rows(conn.execute("""
            SELECT working_class_impact AS impact, COUNT(*) AS count
            FROM divisions WHERE analyzed = 1
            GROUP BY working_class_impact ORDER BY count DESC
        """).fetchall())
        biz = _rows(conn.execute("""
            SELECT business_impact AS impact, COUNT(*) AS count
            FROM divisions WHERE analyzed = 1
            GROUP BY business_impact ORDER BY count DESC
        """).fetchall())

        # Most harmful to working class
        wc_worst = _rows(conn.execute("""
            SELECT d.division_id, d.date, d.title, d.working_class_reason, d.impact_summary,
                   b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.working_class_impact = 'hurts'
            ORDER BY d.date DESC LIMIT 5
        """).fetchall())

        # Most beneficial to working class
        wc_best = _rows(conn.execute("""
            SELECT d.division_id, d.date, d.title, d.working_class_reason, d.impact_summary,
                   b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.working_class_impact = 'helps'
            ORDER BY d.date DESC LIMIT 5
        """).fetchall())

        # Most pro-business
        biz_best = _rows(conn.execute("""
            SELECT d.division_id, d.date, d.title, d.business_reason, d.impact_summary,
                   b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.business_impact = 'helps'
            ORDER BY d.date DESC LIMIT 5
        """).fetchall())

        # Most anti-business
        biz_worst = _rows(conn.execute("""
            SELECT d.division_id, d.date, d.title, d.business_reason, d.impact_summary,
                   b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.business_impact = 'hurts'
            ORDER BY d.date DESC LIMIT 5
        """).fetchall())

        wc_breakdown = _rows(conn.execute("""
            SELECT women_children_impact AS impact, COUNT(*) AS count
            FROM divisions WHERE analyzed = 1 AND women_children_impact IS NOT NULL
            GROUP BY women_children_impact ORDER BY count DESC
        """).fetchall())

        wc_harm = _rows(conn.execute("""
            SELECT d.division_id, d.date, d.title, d.women_children_reason, d.impact_summary,
                   b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.women_children_impact = 'hurts'
            ORDER BY d.date DESC LIMIT 5
        """).fetchall())

        wc_protect = _rows(conn.execute("""
            SELECT d.division_id, d.date, d.title, d.women_children_reason, d.impact_summary,
                   b.short_title AS bill_short_title
            FROM divisions d
            LEFT JOIN division_bills db ON db.division_id = d.division_id
            LEFT JOIN bills b ON b.bill_id = db.bill_id
            WHERE d.women_children_impact = 'helps'
            ORDER BY d.date DESC LIMIT 5
        """).fetchall())

    return {
        "working_class":   {"breakdown": wc,           "recent_harmful":    wc_worst,   "recent_beneficial": wc_best},
        "business":        {"breakdown": biz,           "recent_pro":        biz_best,   "recent_anti":       biz_worst},
        "women_children":  {"breakdown": wc_breakdown,  "recent_harmful":    wc_harm,    "recent_protective": wc_protect},
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    if not os.path.exists(DB_PATH):
        print(f"WARNING: {DB_PATH} not found — run `python fetch.py` first")
    port = int(os.environ.get("PORT", 8125))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=(port == 8125))
