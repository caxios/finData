from findata.server.db.engine import connect
import psycopg2
import psycopg2.extras

from findata.server.db.config import ensure_parent_dir
from findata.server.db.engine import connect as _engine_connect
from findata.server.db import dbutil

# Unique key used for dedup (mirrors the UNIQUE constraint below). On SQLite the
# insert becomes INSERT OR IGNORE; on Postgres, ON CONFLICT (these cols) DO NOTHING.
_TRADE_CONFLICT_COLS = [
    "source_url", "owner_name", "transaction_date", "security_title", "amount",
]


def _to_float(val):
    """Safely convert a string to float, returning None if empty/invalid."""
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def init_db(db_path: str):
    """Create the insider_trades table if it doesn't already exist."""
    ensure_parent_dir(db_path)
    conn = connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insider_trades (
            id                   SERIAL PRIMARY KEY,

            -- Filing-level
            source_url           TEXT,
            document_type        TEXT,
            period_of_report     TEXT,
            ticker               TEXT,
            rss_updated          TEXT,

            -- Issuer
            issuer_name          TEXT,
            issuer_cik           TEXT,
            issuer_symbol        TEXT,

            -- Owner (flattened)
            owner_name           TEXT,
            is_director          TEXT,
            is_officer           TEXT,
            is_ten_pct_owner     TEXT,
            is_other             TEXT,
            officer_title        TEXT,

            -- Transaction (flattened)
            row_type             TEXT,
            security_category    TEXT,
            security_title       TEXT,
            transaction_date     TEXT,
            transaction_code     TEXT,
            transaction_code_description TEXT,
            amount               REAL,
            acquired_or_disposed TEXT,
            price_per_share      REAL,
            shares_owned_after   REAL,
            ownership_form       TEXT,
            nature_of_ownership  TEXT,
            trade_ratio_pct      REAL,
            transaction_value    REAL,
            market_value_after   REAL,
            market_cap           REAL,
            
            UNIQUE(source_url, owner_name, transaction_date, security_title, amount)
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Coverage tracking (plan 05) — which historical windows have been backfilled
# ---------------------------------------------------------------------------
# Without this, "ticker has rows" is mistaken for "ticker's requested period is
# cached", so historical windows (e.g. 2019) would be served incomplete and
# never refetched. Coverage lives in the same DB file as the trades it describes.

def init_coverage_table(db_path: str) -> None:
    """Create the form4_coverage table if it doesn't already exist."""
    ensure_parent_dir(db_path)
    conn = connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS form4_coverage (
            ticker        TEXT NOT NULL,
            covered_from  TEXT NOT NULL,
            covered_to    TEXT NOT NULL,
            recorded_at   TEXT,
            PRIMARY KEY (ticker, covered_from, covered_to)
        );
    """)
    conn.commit()
    conn.close()


def record_coverage(db_path: str, ticker: str, covered_from: str, covered_to: str) -> None:
    """Record that [covered_from, covered_to] has been backfilled for ticker."""
    from datetime import datetime, timezone
    init_coverage_table(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            dbutil.dedup_insert(
                """
                INSERT INTO form4_coverage (ticker, covered_from, covered_to, recorded_at)
                VALUES (%s, %s, %s, %s)
                """,
                conflict_cols=["ticker", "covered_from", "covered_to"],
            ),
            (ticker.upper(), covered_from, covered_to,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_coverage(db_path: str, ticker: str) -> list[tuple[str, str]]:
    """Return recorded coverage windows [(from, to), ...] for a ticker."""
    try:
        conn = connect(db_path)
    except psycopg2.Error:
        return []
    try:
        rows = conn.execute(
            "SELECT covered_from, covered_to FROM form4_coverage WHERE ticker = %s",
            (ticker.upper(),),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except psycopg2.OperationalError:
        return []  # table doesn't exist yet
    finally:
        conn.close()


def is_covered(db_path: str, ticker: str, date_from: str, date_to: str) -> bool:
    """True if a single recorded window fully encloses [date_from, date_to].

    ISO date strings compare lexicographically, so string comparison is correct.
    """
    for cov_from, cov_to in get_coverage(db_path, ticker):
        if cov_from <= date_from and cov_to >= date_to:
            return True
    return False


def save_to_db(parsed_list, db_path: str):
    """
    Flatten parsed Form 4 data (owner x transaction) and insert into SQLite.

    Args:
        parsed_list: List of parsed filing dicts from parse_form4().
        db_path:     Path to the SQLite database file.
    """
    init_db(db_path)
    conn = _engine_connect(db_path)
    cursor = conn.cursor()

    insert_sql = dbutil.dedup_insert(
        """
        INSERT INTO insider_trades (
            source_url, document_type, period_of_report, ticker, rss_updated,
            issuer_name, issuer_cik, issuer_symbol,
            owner_name, is_director, is_officer, is_ten_pct_owner, is_other, officer_title,
            row_type, security_category, security_title, transaction_date, transaction_code,
            transaction_code_description,
            amount, acquired_or_disposed, price_per_share, shares_owned_after,
            ownership_form, nature_of_ownership,
            trade_ratio_pct, transaction_value, market_value_after, market_cap
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        conflict_cols=_TRADE_CONFLICT_COLS,
    )

    inserted = 0
    skipped = 0

    for filing in parsed_list:
        issuer = filing.get("issuer", {})
        rss_meta = filing.get("rss_meta", {})
        owners = filing.get("reporting_owners", [])
        transactions = filing.get("transactions", [])

        # If no owners or no transactions, still nothing to insert
        if not owners or not transactions:
            continue

        for owner in owners:
            rel = owner.get("relationship", {})

            for txn in transactions:
                row = (
                    filing.get("source_url", ""),
                    filing.get("document_type", ""),
                    filing.get("period_of_report", ""),
                    filing.get("ticker", ""),
                    rss_meta.get("updated", ""),

                    issuer.get("name", ""),
                    issuer.get("cik", ""),
                    issuer.get("trading_symbol", ""),

                    owner.get("name", ""),
                    rel.get("is_director", ""),
                    rel.get("is_officer", ""),
                    rel.get("is_ten_pct_owner", ""),
                    rel.get("is_other", ""),
                    rel.get("officer_title", ""),

                    txn.get("row_type", ""),
                    txn.get("security_category", ""),
                    txn.get("security_title", ""),
                    txn.get("transaction_date", ""),
                    txn.get("transaction_code", ""),
                    txn.get("transaction_code_description", ""),
                    _to_float(txn.get("amount")),
                    txn.get("acquired_or_disposed", ""),
                    _to_float(txn.get("price_per_share")),
                    _to_float(txn.get("shares_owned_after")),
                    txn.get("ownership_form", ""),
                    txn.get("nature_of_ownership", ""),
                    _to_float(txn.get("trade_ratio_pct")),
                    _to_float(txn.get("transaction_value")),
                    _to_float(txn.get("market_value_after")),
                    _to_float(txn.get("market_cap")),
                )

                try:
                    cursor.execute(insert_sql, row)
                    if cursor.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1
                except psycopg2.Error as e:
                    print(f"[WARN] DB insert error: {e}")
                    skipped += 1

    conn.commit()
    conn.close()
    print(f"  DB: {inserted} inserted, {skipped} skipped (duplicates) -> {db_path}")
    return inserted, skipped
