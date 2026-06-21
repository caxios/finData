from fastapi import APIRouter, Query, HTTPException, Request
from findata.sec.utils.earnings_call.tavily_transcripts import fetch_transcript
import os
from findata.server.db.config import EARNINGS_DB
from findata.server.db.earnings_db import find_cached
from findata.server.billing import upstream_cost
import sqlite3

# ---------------------------------------------------------------------------
# GET /api/transcript — on-demand earnings call transcript
# ---------------------------------------------------------------------------
router = APIRouter(tags=["EarningsCall"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSCRIPTS_DB = EARNINGS_DB

@router.get("/api/transcript")
def get_transcript(
    request: Request,
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
    # Track 0: a cache miss (or force_refresh) means this call will hit Tavily,
    # which costs real money. Detect that up front so we can record the cost.
    will_hit_upstream = force_refresh or (
        find_cached(TRANSCRIPTS_DB, ticker.upper(), year, quarter) is None
    )

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

    if will_hit_upstream:
        user = getattr(request.state, "user", None)
        try:
            upstream_cost.record_transcript_cost(
                user_id=user["user_id"] if user else None,
                endpoint="/api/transcript",
            )
        except Exception:
            pass  # never fail the request over cost accounting

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
