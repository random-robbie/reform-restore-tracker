#!/usr/bin/env python3
"""
Populate the reform.db database.

Usage:
    python fetch.py            # fetch MPs + votes, then analyse new divisions
    python fetch.py --no-llm   # skip LLM analysis (just pull raw data)
    python fetch.py --analyse  # only run LLM on unanalysed divisions
"""

import time
import argparse

from db import init_db, get_db
from parliament import get_all_mps, get_member_votes
from llm import analyse_division


def upsert_mp(conn, mp: dict):
    conn.execute("""
        INSERT INTO mps (member_id, name, party, party_id, constituency, thumbnail_url)
        VALUES (:member_id, :name, :party, :party_id, :constituency, :thumbnail_url)
        ON CONFLICT(member_id) DO UPDATE SET
            name          = excluded.name,
            party         = excluded.party,
            party_id      = excluded.party_id,
            constituency  = excluded.constituency,
            thumbnail_url = excluded.thumbnail_url,
            fetched_at    = CURRENT_TIMESTAMP
    """, mp)


def upsert_division(conn, div: dict):
    conn.execute("""
        INSERT INTO divisions
            (division_id, date, number, title, aye_count, no_count,
             is_deferred, evel_type, evel_country)
        VALUES
            (:division_id, :date, :number, :title, :aye_count, :no_count,
             :is_deferred, :evel_type, :evel_country)
        ON CONFLICT(division_id) DO UPDATE SET
            aye_count  = excluded.aye_count,
            no_count   = excluded.no_count,
            is_deferred = excluded.is_deferred
    """, div)


def upsert_vote(conn, vote: dict):
    conn.execute("""
        INSERT INTO mp_votes (member_id, division_id, voted_aye, voted_no, was_teller)
        VALUES (:member_id, :division_id, :voted_aye, :voted_no, :was_teller)
        ON CONFLICT(member_id, division_id) DO UPDATE SET
            voted_aye  = excluded.voted_aye,
            voted_no   = excluded.voted_no,
            was_teller = excluded.was_teller
    """, vote)


def _fetch_mp_votes(member_id: int, batch_size: int = 100) -> int:
    """Stream votes from API and commit in batches — safe to interrupt and re-run."""
    total = 0
    batch = []
    for v in _iter_member_votes(member_id):
        batch.append(v)
        if len(batch) >= batch_size:
            _save_batch(batch)
            total += len(batch)
            batch = []
    if batch:
        _save_batch(batch)
        total += len(batch)
    return total


def _iter_member_votes(member_id: int):
    """Yield individual vote records page-by-page from the Parliament API."""
    from parliament import _get, _PAGE, BASE_VOTES
    import time as _time
    skip = 0
    while True:
        data = _get(f"{BASE_VOTES}/divisions.json/membervoting", {
            "queryParameters.memberId": member_id,
            "queryParameters.skip":     skip,
            "queryParameters.take":     _PAGE,
        })
        if not isinstance(data, list) or not data:
            break
        for v in data:
            div      = v.get("PublishedDivision", {})
            date_raw = div.get("Date", "")
            yield {
                "member_id":  member_id,
                "voted_aye":  1 if v.get("MemberVotedAye")  else 0,
                "voted_no":   1 if v.get("MemberVotedNo")   else 0,
                "was_teller": 1 if v.get("MemberWasTeller") else 0,
                "division": {
                    "division_id":  div.get("DivisionId"),
                    "date":         date_raw.split("T")[0] if date_raw else "",
                    "number":       div.get("Number"),
                    "title":        div.get("Title", ""),
                    "aye_count":    div.get("AyeCount") or 0,
                    "no_count":     div.get("NoCount")  or 0,
                    "is_deferred":  1 if div.get("IsDeferred") else 0,
                    "evel_type":    div.get("EVELType", ""),
                    "evel_country": div.get("EVELCountry", ""),
                },
            }
        if len(data) < _PAGE:
            break
        skip += _PAGE
        _time.sleep(0.1)


def _save_batch(votes: list):
    with get_db() as conn:
        for v in votes:
            upsert_division(conn, v["division"])
            upsert_vote(conn, {
                "member_id":   v["member_id"],
                "division_id": v["division"]["division_id"],
                "voted_aye":   v["voted_aye"],
                "voted_no":    v["voted_no"],
                "was_teller":  v["was_teller"],
            })


def fetch_all(skip_llm: bool):
    print("=== Fetching MPs ===")
    mps = get_all_mps()
    print(f"  Found {len(mps)} MPs")

    with get_db() as conn:
        for mp in mps:
            upsert_mp(conn, mp)
    print("  MPs saved")

    print("\n=== Fetching votes ===")
    for mp in mps:
        mid  = mp["member_id"]
        name = mp["name"]
        print(f"  {name} ({mp['party']}) ...", end=" ", flush=True)
        try:
            count = _fetch_mp_votes(mid)
            print(f"{count} votes")
        except Exception as exc:
            print(f"ERROR: {exc}")

    if not skip_llm:
        run_analysis()


def run_analysis():
    print("\n=== Running LLM analysis ===")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT division_id, title, date, aye_count, no_count "
            "FROM divisions WHERE analyzed = 0 ORDER BY date DESC"
        ).fetchall()

    total = len(rows)
    print(f"  {total} divisions to analyse")

    for i, row in enumerate(rows, 1):
        did   = row["division_id"]
        title = row["title"]
        print(f"  [{i}/{total}] {title[:70]} ...", end=" ", flush=True)
        try:
            result = analyse_division(
                title=title,
                date=row["date"] or "",
                aye_count=row["aye_count"] or 0,
                no_count=row["no_count"]  or 0,
            )
            with get_db() as conn:
                conn.execute("""
                    UPDATE divisions SET
                        plain_explanation    = :plain_explanation,
                        working_class_impact = :working_class_impact,
                        working_class_reason = :working_class_reason,
                        business_impact      = :business_impact,
                        business_reason      = :business_reason,
                        public_impact        = :public_impact,
                        impact_summary       = :impact_summary,
                        analyzed             = 1
                    WHERE division_id = :did
                """, {**result, "did": did})
            print("done")
        except Exception as exc:
            print(f"ERROR: {exc}")
        time.sleep(0.5)  # polite pause between LLM calls

    print("Analysis complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm",  action="store_true", help="Skip LLM analysis")
    parser.add_argument("--analyse", action="store_true", help="Only run LLM on unanalysed rows")
    args = parser.parse_args()

    init_db()

    if args.analyse:
        run_analysis()
    else:
        fetch_all(skip_llm=args.no_llm)
