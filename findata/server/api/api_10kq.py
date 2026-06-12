import sys
import asyncio
import os
from findata.server.db.config import SEC_DB_DIR
import sqlite3
from fastapi import Query, HTTPException, Response, APIRouter
from fastapi.responses import JSONResponse
from findata.sec._cik import lookup_cik as _lookup_cik
from findata.server.db.config import SEC_10KQ_DB, COMPANY_FACTS_DB
from findata.server.company_data import (
    SECRateLimit,
    TickerNotFound,
    get_company_data,
)
from findata.sec.company_facts.company_specific_fin import get_company_facts
from findata.server.db.company_facts_db import save_company_facts
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# COMPANY_FACTS_DB imported from findata.server.db.config

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# [에러 해결 핵심 코드] 윈도우 환경일 경우 Proactor 이벤트 루프 정책을 강제로 설정합니다.
if sys.platform == "win32" or "win64":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

router = APIRouter(tags=["10KQ"])

# ---------------------------------------------------------------------------
# GET /api/documents/{ticker} — fetch SEC 10-K/10-Q text sections
# ---------------------------------------------------------------------------
@router.get("/api/documents/{ticker}/list")
def list_documents(ticker: str):
    """Return a list of available 10-K/10-Q filings for a ticker.
    
    DB-first: queries sec_10kq.db. On miss, fetches from SEC EDGAR
    via get_company_data (which scrapes + persists), then re-queries.
    """
    cik, _ = _lookup_cik(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

    def _query_filings(cik_val: str) -> list[dict]:
        if not os.path.exists(SEC_10KQ_DB):
            return []
        conn = sqlite3.connect(SEC_10KQ_DB)
        conn.row_factory = sqlite3.Row
        cik_padded = cik_val.lstrip("0")
        rows = conn.execute(
            """
            SELECT accession_number, form_type, filing_date, company_name
            FROM filing_sections
            WHERE cik IN (?, ?)
            ORDER BY filing_date DESC
            """,
            (cik_val, cik_padded)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    filings = _query_filings(cik)

    # On-demand fetch: if no cached filings, scrape from SEC and retry
    if not filings:
        try:
            get_company_data(ticker, limit_10kq=4)
        except (TickerNotFound, SECRateLimit) as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch from SEC: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Upstream error while fetching: {e!r}")
        filings = _query_filings(cik)

    return {"filings": filings}


@router.get("/api/documents/{ticker}/{accession_number}")
def get_document_detail(ticker: str, accession_number: str):
    """Return MD&A and Risk Factors for a specific filing."""
    if not os.path.exists(SEC_10KQ_DB):
        raise HTTPException(status_code=404, detail="sec_10kq.db not found")
        
    conn = sqlite3.connect(SEC_10KQ_DB)
    conn.row_factory = sqlite3.Row
    
    row = conn.execute(
        """
        SELECT company_name, form_type, filing_date, business, risk_factors, mda
        FROM filing_sections
        WHERE accession_number = ?
        """,
        (accession_number,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Filing not found")

    notes = conn.execute(
        """
        SELECT note_key, note_text
        FROM filing_notes
        WHERE accession_number = ?
        ORDER BY id ASC
        """,
        (accession_number,)
    ).fetchall()
    conn.close()

    return {
        **dict(row),
        "financial_notes": [dict(n) for n in notes],
    }

def _query_financial_periods(cik: str) -> list[dict]:
    if not os.path.exists(COMPANY_FACTS_DB):
        return []
    conn = sqlite3.connect(COMPANY_FACTS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT fy, fp, form, filed, COUNT(*) as fact_count
        FROM company_facts
        WHERE cik = ?
        GROUP BY fy, fp, form, filed
        ORDER BY filed DESC
        """,
        (cik,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/api/financials/{ticker}/list")
def list_financial_periods(ticker: str):
    """
    Return unique filing periods for a ticker.

    DB-first: query company_facts.db. On miss, fetch from SEC EDGAR
    (companyfacts API), persist, then re-query.
    """
    cik, _ = _lookup_cik(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

    periods = _query_financial_periods(cik)
    if not periods:
        try:
            facts = get_company_facts(ticker)
            if facts:
                save_company_facts(facts, COMPANY_FACTS_DB, ticker=ticker.upper())
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch financial facts from SEC: {e!r}",
            )
        periods = _query_financial_periods(cik)

    return {"periods": periods}


def _query_financial_facts(cik: str, fy: int, fp: str, form: str, filed: str) -> list[dict]:
    if not os.path.exists(COMPANY_FACTS_DB):
        return []
    conn = sqlite3.connect(COMPANY_FACTS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT concept, label, val, unit, fy, fp, form, period_end, filed
        FROM company_facts
        WHERE cik = ? AND fy = ? AND fp = ? AND form = ? AND filed = ?
        ORDER BY concept ASC, period_end DESC
        """,
        (cik, fy, fp, form, filed),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/api/financials/{ticker}/detail")
def get_financial_detail(
    ticker: str,
    fy:   int = Query(...),
    fp:   str = Query(...),
    form: str = Query(...),
    filed: str = Query(...)
):
    """
    Return ALL XBRL facts for a specific filing period.

    DB-first: if no rows match, fetch the entire companyfacts payload from
    SEC EDGAR and re-query.
    """
    cik, _ = _lookup_cik(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

    facts = _query_financial_facts(cik, fy, fp, form, filed)
    if not facts:
        try:
            facts = get_company_facts(ticker)
            if facts:
                save_company_facts(facts, COMPANY_FACTS_DB, ticker=ticker.upper())
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch financial facts from SEC: {e!r}",
            )
        facts = _query_financial_facts(cik, fy, fp, form, filed)

    return {"facts": facts}


# ---------------------------------------------------------------------------
# GET /api/company-data/{ticker} — search-driven, DB-first cached lookup
# ---------------------------------------------------------------------------
@router.get("/api/company-data/{ticker}")
def get_company_data_endpoint(
    ticker: str,
    limit: int = Query(
        4,
        ge=1,
        le=1000,
        description="How many 10-K/10-Q filings to return. If the DB has fewer than this, missing filings are scraped from SEC.",
    ),
    limit_form4: int = Query(
        30,
        ge=1,
        le=1000,
        description="How many Form 4 insider trades to return.",
    ),
    include_archive: bool = Query(
        False,
        description="When true, walk the older `filings.files` archives for full 10-K/Q history.",
    ),
):
    """
    Return Form 4 + 10-K/10-Q data for `ticker`.

    Strategy:
      1. Resolve ticker → CIK (404 if unknown).
      2. Check sec_10kq.db / insider_*.db for fresh rows (per-form TTL +
         "DB has at least `limit` 10-K/Q rows").
      3. On miss, fetch from SEC EDGAR, persist, and return.

    Errors:
      404 — unknown ticker
      503 — SEC rate-limited the scrape (Retry-After header set)
      502 — other upstream/parse failure
    """
    try:
        return get_company_data(
            ticker,
            limit_10kq=limit,
            limit_form4=limit_form4,
            include_archive=include_archive,
        )
    except TickerNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SECRateLimit as e:
        return JSONResponse(
            status_code=503,
            content={"detail": str(e), "retry_after": e.retry_after},
            headers={"Retry-After": str(e.retry_after)},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Upstream error: {e!r}")


# ---------------------------------------------------------------------------
# GET /api/sec-filings/{ticker} — generic multi-form filing list (no parsing)
# ---------------------------------------------------------------------------
SUPPORTED_FORMS = {"10-K", "10-Q", "8-K", "S-4", "SC 13D", "SC 13G", "144", "4"}


@router.get("/api/sec-filings/{ticker}")
def list_sec_filings(
    ticker: str,
    forms: str = Query(
        "10-K,10-Q",
        description="Comma-separated form types (e.g. '10-K,10-Q,8-K').",
    ),
    limit: int = Query(20, ge=1, le=1000),
    include_archive: bool = Query(False),
):
    """
    Return filing metadata across the requested form types — pulled live from
    EDGAR's submissions.json (no DB cache, no section parsing). Best for
    populating a filings list UI; pair with form-specific parsing endpoints
    when section text is needed.
    """
    from findata.sec.utils.sec_10kq.sec_10kq_rss import fetch_and_resolve

    cik, _ = _lookup_cik(ticker)
    if not cik:
        raise HTTPException(status_code=404, detail=f"CIK not found for {ticker}")

    requested = {f.strip() for f in forms.split(",") if f.strip()}
    unknown = requested - SUPPORTED_FORMS
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported form types: {sorted(unknown)}. "
                   f"Supported: {sorted(SUPPORTED_FORMS)}",
        )

    try:
        rows = fetch_and_resolve(
            cik, count=limit, include_archive=include_archive, forms=requested,
        )
    except SECRateLimit as e:
        return JSONResponse(
            status_code=503,
            content={"detail": str(e), "retry_after": e.retry_after},
            headers={"Retry-After": str(e.retry_after)},
        )

    # Best-effort: enrich 10-K/10-Q rows with section flags from the cache so
    # the UI can keep showing Business/Risk/MD&A badges where available.
    section_flags: dict[str, dict] = {}
    if {"10-K", "10-Q"} & requested and os.path.exists(SEC_10KQ_DB):
        accs = [r["accession_number"] for r in rows if r["form_type"] in ("10-K", "10-Q")]
        if accs:
            placeholders = ",".join("?" * len(accs))
            conn = sqlite3.connect(SEC_10KQ_DB)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                f"""
                SELECT accession_number,
                       (business     IS NOT NULL AND length(business)     > 0) AS has_business,
                       (risk_factors IS NOT NULL AND length(risk_factors) > 0) AS has_risk_factors,
                       (mda          IS NOT NULL AND length(mda)          > 0) AS has_mda
                  FROM filing_sections
                 WHERE accession_number IN ({placeholders})
                """,
                accs,
            )
            for r in cur.fetchall():
                section_flags[r["accession_number"]] = {
                    "has_business": bool(r["has_business"]),
                    "has_risk_factors": bool(r["has_risk_factors"]),
                    "has_mda": bool(r["has_mda"]),
                }
            conn.close()

    out = []
    for r in rows:
        flags = section_flags.get(r["accession_number"], {
            "has_business": False, "has_risk_factors": False, "has_mda": False,
        })
        out.append({**r, **flags})

    return {"ticker": ticker.upper(), "cik": cik, "filings": out}


# ---------------------------------------------------------------------------
# GET /api/filing-text/{accession_number} — parsed text for non-10-K/Q forms
# ---------------------------------------------------------------------------
@router.get("/api/filing-text/{accession_number}")
def get_filing_text(
    accession_number: str,
    form: str = Query(..., description="Form type, e.g. '8-K', 'S-4', 'SC 13D', '144'."),
    document_url: str = Query(..., description="Primary document URL."),
    ticker: str | None = Query(None, description="Used to resolve CIK on a fresh parse."),
    filing_date: str | None = Query(None),
):
    """
    Return parsed sections for one filing of the supported non-10-K/Q forms.
    On cache miss this downloads the primary document, parses it with the
    form-specific parser, and persists to that form's DB.
    """
    from sec_filings.dispatcher import get_or_parse, PARSEABLE_FORMS

    if form not in PARSEABLE_FORMS:
        raise HTTPException(
            status_code=400,
            detail=f"Form {form!r} is not parseable here. "
                   f"Use /api/documents/* for 10-K/10-Q.",
        )

    cik = None
    if ticker:
        cik, _ = _lookup_cik(ticker)

    result = get_or_parse(
        form=form,
        accession_number=accession_number,
        document_url=document_url,
        cik=cik,
        filing_date=filing_date,
    )
    if not result:
        raise HTTPException(status_code=502, detail="Failed to parse filing.")
    return result


@router.get("/api/download-pdf")
def generate_pdf(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        # [핵심 해결책] SEC가 요구하는 규격의 명찰(User-Agent)을 달고 새 창을 엽니다.
        # [수정 포인트 1] 괄호와 기호를 모두 뺀 가장 안전하고 단순한 포맷
        sec_user_agent = "DK mrsimple@gmail.com"
        
        context = browser.new_context(
            user_agent=sec_user_agent,
            extra_http_headers={
                "User-Agent": sec_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
        )
        # browser가 아닌 context에서 페이지를 생성해야 명찰이 적용됩니다.
        page = context.new_page()
        # 1. SEC 페이지 접속
        page.goto(url)
        # [수정 포인트 3] SEC 방화벽이 페이지를 렌더링하고 차단을 풀 시간을 주기 위한 1.5초 대기
        page.wait_for_timeout(1500)
        # 2. 물리적 저장이 아닌, 메모리 상의 바이트(Bytes)로 PDF 구워내기
        pdf_bytes = page.pdf(format="A4") 
        browser.close()
        # 3. DB에 저장하지 않고 생성된 바이트를 유저에게 그대로 전송!
        return Response(content=pdf_bytes, media_type="application/pdf")