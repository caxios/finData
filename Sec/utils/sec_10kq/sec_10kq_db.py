"""
sec_10kq_db.py
──────────────
Database layer for the 10-K / 10-Q text extraction pipeline.

Two tables:
  - filing_sections:   One row per filing with extracted section text.
  - filing_notes:      One row per crucial financial note (child rows).
"""

import json
import sqlite3


def init_db(db_path: str):
    """Create the tables if they don't exist."""
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS filing_sections (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Filing metadata
            cik                 TEXT,
            company_name        TEXT,
            form_type           TEXT,
            filing_date         TEXT,
            accession_number    TEXT,
            index_url           TEXT,
            document_url        TEXT,
            parse_method        TEXT,

            -- Extracted sections (full text, can be very large)
            business            TEXT,
            risk_factors        TEXT,
            mda                 TEXT,

            -- Timestamps
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(accession_number)
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS filing_notes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,

            -- FK to filing
            accession_number    TEXT NOT NULL,

            -- Note details
            note_key            TEXT,
            note_text           TEXT,

            UNIQUE(accession_number, note_key),
            FOREIGN KEY (accession_number) REFERENCES filing_sections(accession_number)
        );
    """)

    conn.commit()
    conn.close()


def save_filing(parsed_filing: dict, db_path: str) -> bool:
    """
    Save a single parsed filing result to the database.

    Args:
        parsed_filing: Dict returned by sec_10kq_parser.parse_single_filing().
        db_path:       Path to the SQLite database file.

    Returns:
        True if the filing was inserted, False if skipped (duplicate).
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    sections = parsed_filing.get("sections") or {}
    acc = parsed_filing.get("accession_number", "")

    # --- Insert main filing row ---
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO filing_sections (
                cik, company_name, form_type, filing_date, accession_number,
                index_url, document_url, parse_method,
                business, risk_factors, mda
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parsed_filing.get("cik", ""),
            parsed_filing.get("title", ""),
            parsed_filing.get("form_type", ""),
            parsed_filing.get("filing_date", ""),
            acc,
            parsed_filing.get("index_url", ""),
            parsed_filing.get("document_url", ""),
            parsed_filing.get("parse_method", ""),
            sections.get("business"),
            sections.get("risk_factors"),
            sections.get("mda"),
        ))

        if cursor.rowcount == 0:
            conn.close()
            return False  # duplicate

    except sqlite3.Error as e:
        print(f"  [WARN] DB insert error (filing_sections): {e}")
        conn.close()
        return False

    # --- Insert financial notes (one row per note) ---
    notes = sections.get("financial_notes")
    if isinstance(notes, dict):
        for note_key, note_text in notes.items():
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO filing_notes (
                        accession_number, note_key, note_text
                    ) VALUES (?, ?, ?)
                """, (acc, note_key, note_text))
            except sqlite3.Error as e:
                print(f"  [WARN] DB insert error (filing_notes): {e}")

    conn.commit()
    conn.close()
    return True


def save_batch(parsed_filings: list[dict], db_path: str) -> tuple[int, int]:
    """
    Save a list of parsed filings to the database.

    Returns:
        (inserted_count, skipped_count)
    """
    inserted = 0
    skipped = 0

    for filing in parsed_filings:
        if filing.get("sections") is None:
            skipped += 1
            continue

        if save_filing(filing, db_path):
            inserted += 1
        else:
            skipped += 1

    print(f"  DB: {inserted} inserted, {skipped} skipped (duplicates/errors) -> {db_path}")
    return inserted, skipped


def get_filing_count(db_path: str) -> int:
    """Return the total number of filings stored."""
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM filing_sections").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def get_filings_by_cik(cik: str, db_path: str) -> list[dict]:
    """Retrieve all stored filings for a given CIK."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM filing_sections WHERE cik = ? ORDER BY filing_date DESC",
            (cik,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_notes_for_filing(accession_number: str, db_path: str) -> list[dict]:
    """Retrieve all crucial notes for a given filing."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM filing_notes WHERE accession_number = ?",
            (accession_number,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []
