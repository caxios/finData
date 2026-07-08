import sys
import asyncio
import os
from fastapi import Query, HTTPException, Response, APIRouter
from fastapi.responses import JSONResponse
from findata.sec._cik import lookup_cik as _lookup_cik
from findata.server.db.config import SEC_10KQ_DB, COMPANY_FACTS_DB
from findata.server.db.engine import connect as _db_connect
from findata.server.company_data import (
    SECRateLimit,
    TickerNotFound,
    get_company_data,
)
from findata.sec.company_facts.company_specific_fin import get_company_facts
from findata.server.db.company_facts_db import save_company_facts
# NOTE: playwright is imported lazily inside generate_pdf() so the app (and its
# container image) doesn't require Chromium unless PDF rendering is enabled.
# See ENABLE_PDF_DOWNLOAD below and 08_deployment_and_infra.md §3.2 / Step 1.


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# COMPANY_FACTS_DB imported from findata.server.db.config

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# [에러 해결 핵심 코드] 윈도우 환경일 경우 Proactor 이벤트 루프 정책을 강제로 설정합니다.
if sys.platform in ("win32", "win64"):
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
        cik_padded = cik_val.lstrip("0")
        try:
            conn = _db_connect(SEC_10KQ_DB)
        except Exception:
            return []
        try:
            rows = conn.execute(
                """
                SELECT accession_number, form_type, filing_date, company_name
                FROM filing_sections
                WHERE cik IN (%s, %s)
                ORDER BY filing_date DESC
                """,
                (cik_val, cik_padded)
            ).fetchall()
        except Exception:
            rows = []
        finally:
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
    conn = _db_connect(SEC_10KQ_DB)

    row = conn.execute(
        """
        SELECT company_name, form_type, filing_date, business, risk_factors, mda
        FROM filing_sections
        WHERE accession_number = %s
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
        WHERE accession_number = %s
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
    try:
        conn = _db_connect(COMPANY_FACTS_DB)
    except Exception:
        return []
    try:
        rows = conn.execute(
            """
            SELECT fy, fp, form, filed, COUNT(*) as fact_count
            FROM company_facts
            WHERE cik = %s
              AND fy IS NOT NULL
              AND fp IS NOT NULL
            GROUP BY fy, fp, form, filed
            ORDER BY filed DESC
            """,
            (cik,),
        ).fetchall()
    except Exception:
        rows = []
    finally:
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
    try:
        conn = _db_connect(COMPANY_FACTS_DB)
    except Exception:
        return []
    try:
        rows = conn.execute(
            """
            SELECT concept, label, val, unit, fy, fp, form, period_end, filed
            FROM company_facts
            WHERE cik = %s AND fy = %s AND fp = %s AND form = %s AND filed = %s
            ORDER BY concept ASC, period_end DESC
            """,
            (cik, fy, fp, form, filed),
        ).fetchall()
    except Exception:
        rows = []
    finally:
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
    from findata.sec.utils.sec_submissions import fetch_and_resolve

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
    if {"10-K", "10-Q"} & requested:
        accs = [r["accession_number"] for r in rows if r["form_type"] in ("10-K", "10-Q")]
        if accs:
            placeholders = ",".join(["%s"] * len(accs))
            try:
                conn = _db_connect(SEC_10KQ_DB)
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
            except Exception:
                pass

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
    from findata.sec.utils.sec_filings.dispatcher import get_or_parse, PARSEABLE_FORMS

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
def generate_pdf(
    url: str | None = Query(
        None,
        description="Direct primary-document URL. Optional — prefer `ticker` so "
                    "you don't have to build a SEC URL by hand.",
    ),
    ticker: str | None = Query(
        None,
        description="Resolve filings by ticker instead of a raw URL.",
    ),
    forms: str = Query(
        "10-K",
        description="Form type(s) to resolve when `ticker` is given (comma-separated).",
    ),
    date_from: str | None = Query(
        None, description="Inclusive lower bound (YYYY-MM-DD) when resolving by ticker."
    ),
    date_to: str | None = Query(
        None, description="Inclusive upper bound (YYYY-MM-DD) when resolving by ticker."
    ),
    include_archive: bool | None = Query(
        None,
        description="Walk archive shards for older filings. Defaults to on when a "
                    "date window is given.",
    ),
):
    """Render SEC filing(s) to PDF.

    Two ways to target the filing(s) — you never need to build the URL yourself:

    - **By ticker (recommended):** pass `ticker` (+ optional `forms`, `date_from`,
      `date_to`). With no date window you get the single latest filing; with a
      window you get every filing in it. A single match returns a PDF; multiple
      matches return a ZIP (one PDF per filing).
    - **By URL (fallback):** pass a raw primary-document `url`.
    """
    # Disabled by default: Playwright/Chromium is heavy and not installed in the
    # slim image. Enable with ENABLE_PDF_DOWNLOAD=1 on a host with the browser.
    if os.getenv("ENABLE_PDF_DOWNLOAD", "0") != "1":
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "PDF_DISABLED",
                    "message": (
                        "PDF rendering is disabled on this server. "
                        "Set ENABLE_PDF_DOWNLOAD=1 (requires Playwright + Chromium)."
                    ),
                }
            },
        )

    if not ticker and not url:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "MISSING_TARGET",
                    "message": "Provide either `ticker` (recommended) or `url`.",
                }
            },
        )

    # Resolve the target URL(s). By ticker, use the shared library resolver so
    # URL construction matches the rest of the system (submissions.json →
    # primary document). By raw URL, use it directly.
    if ticker:
        from findata.sec.filings import find_filings

        try:
            rows = find_filings(
                ticker,
                form_type=forms,
                date_from=date_from,
                date_to=date_to,
                count=1,  # no window → latest 1; windowed → all in range
                include_archive=include_archive,
            )
        except ValueError as e:  # unknown ticker
            raise HTTPException(status_code=404, detail=str(e))
        urls = [r["document_url"] for r in rows if r.get("document_url")]
        if not urls:
            raise HTTPException(
                status_code=404,
                detail=f"No {forms} filing found for {ticker!r} "
                       f"(date_from={date_from}, date_to={date_to}).",
            )
    else:
        urls = [url]

    # Render via the library layer (single URL → PDF bytes, multiple → ZIP bytes).
    from findata.sec.pdf import download_filing_pdf, SECAccessBlocked

    try:
        data = download_filing_pdf(urls)
    except SECAccessBlocked as e:
        # SEC rate-limited us — surface as 429 so callers can back off, and
        # don't hand back a PDF of the block page.
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "SEC_RATE_LIMITED", "message": str(e)}},
            headers={"Retry-After": "300"},
        )
    except RuntimeError as e:  # Playwright not installed
        raise HTTPException(status_code=503, detail=str(e))

    if len(urls) > 1:
        filename = f"{(ticker or 'filings').upper()}_filings.zip"
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return Response(content=data, media_type="application/pdf")
