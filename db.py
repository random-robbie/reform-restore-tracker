import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "reform.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mps (
    member_id   INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    party       TEXT NOT NULL,
    party_id    INTEGER,
    constituency TEXT,
    thumbnail_url TEXT,
    fetched_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS divisions (
    division_id      INTEGER PRIMARY KEY,
    date             TEXT,
    number           INTEGER,
    title            TEXT NOT NULL,
    aye_count        INTEGER,
    no_count         INTEGER,
    is_deferred      INTEGER DEFAULT 0,
    evel_type        TEXT,
    evel_country     TEXT,
    -- LLM analysis
    plain_explanation      TEXT,
    working_class_impact   TEXT,
    working_class_reason   TEXT,
    business_impact        TEXT,
    business_reason        TEXT,
    women_children_impact  TEXT,
    women_children_reason  TEXT,
    public_impact          TEXT,
    impact_summary         TEXT,
    analyzed               INTEGER DEFAULT 0,
    created_at           TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mp_votes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id   INTEGER NOT NULL REFERENCES mps(member_id),
    division_id INTEGER NOT NULL REFERENCES divisions(division_id),
    voted_aye   INTEGER DEFAULT 0,
    voted_no    INTEGER DEFAULT 0,
    was_teller  INTEGER DEFAULT 0,
    UNIQUE(member_id, division_id)
);

CREATE TABLE IF NOT EXISTS bills (
    bill_id           INTEGER PRIMARY KEY,
    short_title       TEXT NOT NULL,
    long_title        TEXT,
    current_stage     TEXT,
    current_house     TEXT,
    originating_house TEXT,
    is_act            INTEGER DEFAULT 0,
    is_defeated       INTEGER DEFAULT 0,
    last_update       TEXT,
    fetched_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS division_bills (
    division_id INTEGER NOT NULL REFERENCES divisions(division_id),
    bill_id     INTEGER NOT NULL REFERENCES bills(bill_id),
    PRIMARY KEY (division_id, bill_id)
);

CREATE INDEX IF NOT EXISTS idx_votes_member   ON mp_votes(member_id);
CREATE INDEX IF NOT EXISTS idx_votes_division ON mp_votes(division_id);
CREATE INDEX IF NOT EXISTS idx_div_date       ON divisions(date);
CREATE INDEX IF NOT EXISTS idx_div_analyzed   ON divisions(analyzed);
CREATE INDEX IF NOT EXISTS idx_divbills_bill  ON division_bills(bill_id);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"DB ready: {DB_PATH}")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
