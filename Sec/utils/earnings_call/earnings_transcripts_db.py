import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse


def init_db(db_path: str):
    """Create earnings_transcripts table + FTS5 mirror if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_transcripts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            fiscal_year     INTEGER NOT NULL,
            fiscal_quarter  INTEGER NOT NULL,
            cik             TEXT,
            call_date       TEXT,
            source_url      TEXT    NOT NULL,
            source_domain   TEXT,
            title           TEXT,
            transcript_text TEXT    NOT NULL,
            fetched_at      TEXT    NOT NULL,
            UNIQUE(ticker, fiscal_year, fiscal_quarter, source_url)
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_transcripts_lookup
            ON earnings_transcripts(ticker, fiscal_year, fiscal_quarter);
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS earnings_transcripts_fts
        USING fts5(
            transcript_text, ticker,
            content='earnings_transcripts', content_rowid='id'
        );
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS earnings_transcripts_ai
        AFTER INSERT ON earnings_transcripts BEGIN
            INSERT INTO earnings_transcripts_fts(rowid, transcript_text, ticker)
            VALUES (new.id, new.transcript_text, new.ticker);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS earnings_transcripts_ad
        AFTER DELETE ON earnings_transcripts BEGIN
            INSERT INTO earnings_transcripts_fts(earnings_transcripts_fts, rowid, transcript_text, ticker)
            VALUES ('delete', old.id, old.transcript_text, old.ticker);
        END;
    """)
    conn.commit()
    conn.close()


def find_cached(db_path: str, ticker: str, fiscal_year: int, fiscal_quarter: int):
    """Return the most-recent cached transcript row for this (ticker, year, quarter), or None."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT * FROM earnings_transcripts
        WHERE ticker = ? AND fiscal_year = ? AND fiscal_quarter = ?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (ticker.upper(), fiscal_year, fiscal_quarter),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_transcript(db_path: str, *, ticker: str, fiscal_year: int, fiscal_quarter: int,
                    source_url: str, transcript_text: str,
                    title: str = None, call_date: str = None, cik: str = None) -> dict:
    """Insert one transcript row; returns the saved row as a dict."""
    init_db(db_path)
    domain = urlparse(source_url).netloc.lower().lstrip("www.")
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO earnings_transcripts (
            ticker, fiscal_year, fiscal_quarter, cik, call_date,
            source_url, source_domain, title, transcript_text, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ticker.upper(), fiscal_year, fiscal_quarter, cik, call_date,
         source_url, domain, title, transcript_text, fetched_at),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT * FROM earnings_transcripts
        WHERE ticker = ? AND fiscal_year = ? AND fiscal_quarter = ? AND source_url = ?
        """,
        (ticker.upper(), fiscal_year, fiscal_quarter, source_url),
    ).fetchone()
    conn.close()
    return dict(row) if row else None