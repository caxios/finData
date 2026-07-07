from findata.server.db.engine import connect
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from urllib.parse import urlparse

from findata.server.db.config import ensure_parent_dir


def init_db(db_path: str):
    """Create earnings_transcripts table + FTS5 mirror if they don't exist."""
    ensure_parent_dir(db_path)
    conn = connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS earnings_transcripts (
            id              SERIAL PRIMARY KEY,
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

    conn.commit()
    conn.close()


def find_cached(db_path: str, ticker: str, fiscal_year: int, fiscal_quarter: int):
    """Return the most-recent cached transcript row for this (ticker, year, quarter), or None."""
    init_db(db_path)
    conn = connect(db_path)
    
    row = conn.execute(
        """
        SELECT * FROM earnings_transcripts
        WHERE ticker = %s AND fiscal_year = %s AND fiscal_quarter = %s
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

    conn = connect(db_path)
    
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO earnings_transcripts (
            ticker, fiscal_year, fiscal_quarter, cik, call_date,
            source_url, source_domain, title, transcript_text, fetched_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker, fiscal_year, fiscal_quarter, source_url) DO NOTHING
        """,
        (ticker.upper(), fiscal_year, fiscal_quarter, cik, call_date,
         source_url, domain, title, transcript_text, fetched_at),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT * FROM earnings_transcripts
        WHERE ticker = %s AND fiscal_year = %s AND fiscal_quarter = %s AND source_url = %s
        """,
        (ticker.upper(), fiscal_year, fiscal_quarter, source_url),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
