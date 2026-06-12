import sqlite3


def init_db(db_path: str):
    """Create companies + company_facts tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            cik         TEXT PRIMARY KEY,
            ticker      TEXT,
            entity_name TEXT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS company_facts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            cik          TEXT NOT NULL,
            taxonomy     TEXT NOT NULL,
            concept      TEXT NOT NULL,
            label        TEXT,
            unit         TEXT NOT NULL,
            period_start TEXT,
            period_end   TEXT NOT NULL,
            val          REAL NOT NULL,
            accn         TEXT,
            fy           INTEGER,
            fp           TEXT,
            form         TEXT,
            filed        TEXT,
            frame        TEXT,
            UNIQUE(cik, taxonomy, concept, unit, period_end, accn)
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_facts_lookup
            ON company_facts(cik, taxonomy, concept, period_end);
    """)
    conn.commit()
    conn.close()


def save_company_facts(facts_data, db_path: str, ticker: str = None):
    """
    Flatten the SEC EDGAR companyfacts JSON into rows and insert into SQLite.

    Each (taxonomy, concept, unit, observation) tuple becomes one row.
    Re-running on the same data is a no-op thanks to the UNIQUE constraint.

    Returns (inserted, skipped).
    """
    init_db(db_path)

    cik = str(facts_data["cik"]).zfill(10)
    entity_name = facts_data.get("entityName")

    rows = []
    for taxonomy, concepts in facts_data.get("facts", {}).items():
        for concept, payload in concepts.items():
            label = payload.get("label")
            for unit, observations in payload.get("units", {}).items():
                for obs in observations:
                    if "end" not in obs or "val" not in obs:
                        continue
                    rows.append((
                        cik, taxonomy, concept, label, unit,
                        obs.get("start"), obs["end"], obs["val"],
                        obs.get("accn"), obs.get("fy"), obs.get("fp"),
                        obs.get("form"), obs.get("filed"), obs.get("frame"),
                    ))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR REPLACE INTO companies (cik, ticker, entity_name) VALUES (?, ?, ?)",
        (cik, ticker, entity_name),
    )

    before = conn.total_changes
    cursor.executemany("""
        INSERT OR IGNORE INTO company_facts (
            cik, taxonomy, concept, label, unit,
            period_start, period_end, val,
            accn, fy, fp, form, filed, frame
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    inserted = conn.total_changes - before - 1  # minus the companies upsert
    skipped = len(rows) - inserted
    conn.close()

    print(f"  DB: {inserted} inserted, {skipped} skipped (duplicates) -> {db_path}")
    return inserted, skipped
