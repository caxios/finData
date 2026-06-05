"""
Per-form SQLite layer for the additional SEC filing types.

One DB file per form so each pipeline is independently versionable:
  - db/sec_8k.db    — 8-K filings (items as JSON blob)
  - db/sec_s4.db    — S-4 filings (free-form sections)
  - db/sec_13.db    — SC 13D / SC 13G (cover-page extracted fields)
  - db/sec_144.db   — Form 144 (structured XML fields)
"""

import json
import os
import sqlite3
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "db")

DB_PATHS = {
    "8-K":    os.path.join(DB_DIR, "sec_8k.db"),
    "S-4":    os.path.join(DB_DIR, "sec_s4.db"),
    "SC 13D": os.path.join(DB_DIR, "sec_13.db"),
    "SC 13G": os.path.join(DB_DIR, "sec_13.db"),
    "144":    os.path.join(DB_DIR, "sec_144.db"),
}

# Common metadata columns shared across every per-form table.
_META = """
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cik               TEXT,
    accession_number  TEXT UNIQUE,
    form_type         TEXT,
    filing_date       TEXT,
    document_url      TEXT,
    full_text         TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
"""

_SCHEMAS = {
    "8-K": f"""
        CREATE TABLE IF NOT EXISTS filings_8k (
            {_META},
            items_json    TEXT  -- JSON: [{{"code": "1.01", "title": "...", "text": "..."}}]
        );
    """,
    "S-4": f"""
        CREATE TABLE IF NOT EXISTS filings_s4 (
            {_META},
            sections_json TEXT  -- JSON: {{"summary": "...", "risk_factors": "...", "the_merger": "..."}}
        );
    """,
    "SC 13": f"""
        CREATE TABLE IF NOT EXISTS filings_sc13 (
            {_META},
            beneficial_owner   TEXT,
            shares_owned       TEXT,
            percent_owned      TEXT
        );
    """,
    "144": f"""
        CREATE TABLE IF NOT EXISTS filings_144 (
            {_META},
            issuer_name        TEXT,
            shares_to_be_sold  TEXT,
            aggregate_value    TEXT,
            broker             TEXT,
            sale_date          TEXT
        );
    """,
}

_TABLE = {
    "8-K":    "filings_8k",
    "S-4":    "filings_s4",
    "SC 13D": "filings_sc13",
    "SC 13G": "filings_sc13",
    "144":    "filings_144",
}


def _schema_key(form: str) -> str:
    return "SC 13" if form in ("SC 13D", "SC 13G") else form


def _connect(form: str) -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    db_path = DB_PATHS[form]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMAS[_schema_key(form)])
    return conn


def save_filing(form: str, parsed: dict[str, Any]) -> bool:
    """Insert a parsed filing. Returns False if already present (UNIQUE accession_number)."""
    table = _TABLE[form]
    conn = _connect(form)
    try:
        common = (
            parsed.get("cik"),
            parsed.get("accession_number"),
            parsed.get("form_type", form),
            parsed.get("filing_date"),
            parsed.get("document_url"),
            parsed.get("full_text"),
        )
        if form == "8-K":
            sql = (f"INSERT OR IGNORE INTO {table} "
                   f"(cik, accession_number, form_type, filing_date, document_url, full_text, items_json) "
                   f"VALUES (?, ?, ?, ?, ?, ?, ?)")
            extras = (json.dumps(parsed.get("items", []), ensure_ascii=False),)
        elif form == "S-4":
            sql = (f"INSERT OR IGNORE INTO {table} "
                   f"(cik, accession_number, form_type, filing_date, document_url, full_text, sections_json) "
                   f"VALUES (?, ?, ?, ?, ?, ?, ?)")
            extras = (json.dumps(parsed.get("sections", {}), ensure_ascii=False),)
        elif form in ("SC 13D", "SC 13G"):
            sql = (f"INSERT OR IGNORE INTO {table} "
                   f"(cik, accession_number, form_type, filing_date, document_url, full_text, "
                   f" beneficial_owner, shares_owned, percent_owned) "
                   f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
            extras = (
                parsed.get("beneficial_owner"),
                parsed.get("shares_owned"),
                parsed.get("percent_owned"),
            )
        elif form == "144":
            sql = (f"INSERT OR IGNORE INTO {table} "
                   f"(cik, accession_number, form_type, filing_date, document_url, full_text, "
                   f" issuer_name, shares_to_be_sold, aggregate_value, broker, sale_date) "
                   f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
            extras = (
                parsed.get("issuer_name"),
                parsed.get("shares_to_be_sold"),
                parsed.get("aggregate_value"),
                parsed.get("broker"),
                parsed.get("sale_date"),
            )
        else:
            raise ValueError(f"Unknown form for save_filing: {form}")

        cur = conn.execute(sql, common + extras)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def select_filing(form: str, accession_number: str) -> dict[str, Any] | None:
    """Return the cached row for `accession_number` or None."""
    table = _TABLE[form]
    conn = _connect(form)
    try:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE accession_number = ?",
            (accession_number,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    out = dict(row)
    # Inflate JSON columns.
    if form == "8-K":
        out["items"] = json.loads(out.pop("items_json") or "[]")
    elif form == "S-4":
        out["sections"] = json.loads(out.pop("sections_json") or "{}")
    return out
