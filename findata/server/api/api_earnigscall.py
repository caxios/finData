from fastapi import APIRouter, Query, HTTPException
from findata.sec.utils.earnings_call.tavily_transcripts import fetch_transcript
import os
from findata.server.db.config import SEC_DB_DIR
import sqlite3

# ---------------------------------------------------------------------------
# GET /api/transcript — on-demand earnings call transcript
# ---------------------------------------------------------------------------
router = APIRouter(tags=["EarningsCall"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPTS_DB = os.path.join(SEC_DB_DIR, "earnings_transcripts.db")

@router.get("/api/transcript")
def get_transcript(
    ticker: str,
    year:   int = Query(..., description="Fiscal year, e.g. 2024"),
    quarter: int = Query(..., ge=1, le=4, description="Fiscal quarter 1-4"),
    force_refresh: bool = Query(False, description="Bypass cache and re-fetch"),
):
    """
    Return the earnings call transcript for ticker/year/quarter.

    On first call, searches via Tavily and caches the result. Subsequent calls
    return the cached row unless force_refresh=true.
    """
    try:
        row = fetch_transcript(
            ticker=ticker,
            fiscal_year=year,
            fiscal_quarter=quarter,
            db_path=TRANSCRIPTS_DB,
            force_refresh=force_refresh,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not row:
        raise HTTPException(status_code=404, detail="No transcript found")
    return row


@router.get("/api/transcripts/{ticker}/list")
def list_transcripts(ticker: str):
    """Return a list of available earnings call transcripts for a ticker."""
    if not os.path.exists(TRANSCRIPTS_DB):
        return {"transcripts": []}
        
    conn = sqlite3.connect(TRANSCRIPTS_DB)
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute(
        """
        SELECT fiscal_year, fiscal_quarter, call_date, title
        FROM earnings_transcripts
        WHERE ticker = ?
        ORDER BY fiscal_year DESC, fiscal_quarter DESC
        """,
        (ticker.upper(),)
    ).fetchall()
    conn.close()
    
    return {"transcripts": [dict(r) for r in rows]}