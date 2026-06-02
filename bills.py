#!/usr/bin/env python3
"""
Fetch bill details from the Parliament Bills API and link them to divisions.

Run standalone:  python bills.py
Or import:       from bills import sync_bills
"""

import time
import requests
from db import get_db

BILLS_API = "https://bills-api.parliament.uk/api/v1/Bills"


def _get(url: str, params: dict | None = None) -> dict | list:
    r = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    return r.json()


def _extract_bill_name(division_title: str) -> str:
    """Return the part of the division title that names the bill (before the colon)."""
    name = division_title.split(":")[0].strip()
    # Skip motion/procedural titles that aren't bills
    skip = {"opposition day", "king's speech", "queen's speech", "privilege",
            "ten minute rule", "business of the house", "emergency debate",
            "adjournment", "deferred division", "money resolution"}
    if name.lower() in skip or not any(w in name.lower() for w in ("bill", "act", "regulations", "order")):
        return ""
    return name


def _search_bill(name: str) -> dict | None:
    """Search for a bill by name; return the best match or None."""
    try:
        data = _get(BILLS_API, {"SearchTerm": name, "take": 3})
        items = data.get("items", [])
        if not items:
            return None
        # Prefer exact short-title match, else take first result
        for item in items:
            if item.get("shortTitle", "").lower() == name.lower():
                return item
        return items[0]
    except Exception:
        return None


def _fetch_long_title(bill_id: int) -> str:
    try:
        data = _get(f"{BILLS_API}/{bill_id}")
        return (data.get("longTitle") or "").strip()
    except Exception:
        return ""


def sync_bills(verbose: bool = True) -> int:
    """
    For every division whose title suggests a bill, look up the bill in the
    Parliament Bills API and store it.  Returns number of new bills linked.
    """
    with get_db() as conn:
        # Only process divisions not yet linked to a bill
        rows = conn.execute("""
            SELECT d.division_id, d.title
            FROM divisions d
            WHERE NOT EXISTS (
                SELECT 1 FROM division_bills db WHERE db.division_id = d.division_id
            )
            ORDER BY d.date DESC
        """).fetchall()

    if verbose:
        print(f"  {len(rows)} unlinked divisions to check")

    linked = 0
    checked: dict[str, int | None] = {}  # bill_name → bill_id or None

    for row in rows:
        div_id = row["division_id"]
        title  = row["title"]
        name   = _extract_bill_name(title)
        if not name:
            continue

        if name in checked:
            bill_id = checked[name]
        else:
            match = _search_bill(name)
            if match:
                bill_id = match["billId"]
                long_title = _fetch_long_title(bill_id)
                stage = ""
                if match.get("currentStage"):
                    stage = match["currentStage"].get("description", "")
                with get_db() as conn:
                    conn.execute("""
                        INSERT INTO bills
                            (bill_id, short_title, long_title, current_stage,
                             current_house, originating_house, is_act, is_defeated, last_update)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(bill_id) DO UPDATE SET
                            short_title   = excluded.short_title,
                            long_title    = excluded.long_title,
                            current_stage = excluded.current_stage,
                            current_house = excluded.current_house,
                            is_act        = excluded.is_act,
                            is_defeated   = excluded.is_defeated,
                            last_update   = excluded.last_update,
                            fetched_at    = CURRENT_TIMESTAMP
                    """, (
                        bill_id,
                        match.get("shortTitle", name),
                        long_title,
                        stage,
                        match.get("currentHouse", ""),
                        match.get("originatingHouse", ""),
                        1 if match.get("isAct") else 0,
                        1 if match.get("isDefeated") else 0,
                        (match.get("lastUpdate") or "")[:10],
                    ))
                checked[name] = bill_id
                if verbose:
                    print(f"    Linked bill: {name[:60]}")
                time.sleep(0.15)
            else:
                checked[name] = None
                bill_id = None

        if bill_id:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO division_bills (division_id, bill_id)
                    VALUES (?, ?)
                """, (div_id, bill_id))
            linked += 1

    return linked


if __name__ == "__main__":
    from db import init_db
    init_db()
    print("=== Syncing bills ===")
    n = sync_bills(verbose=True)
    print(f"  Done — {n} division→bill links created")
