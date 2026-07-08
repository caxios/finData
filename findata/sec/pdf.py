"""
SEC filing PDF download — library layer.

Renders SEC filing pages to PDF using Playwright (headless Chromium).
Supports single URL (returns PDF bytes) and multiple URLs (returns ZIP bytes).

Usage::

    import findata

    # Single URL → PDF bytes
    pdf_bytes = findata.download_filing_pdf(
        "https://www.sec.gov/Archives/edgar/data/320193/..."
    )

    # Multiple URLs → ZIP bytes containing all PDFs
    zip_bytes = findata.download_filing_pdf([
        "https://www.sec.gov/Archives/edgar/data/320193/...",
        "https://www.sec.gov/Archives/edgar/data/320193/...",
    ], output_path="filings.zip")

Requires: pip install "findata[server]" (Playwright + Chromium)
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse, unquote

from findata.sec.const import SEC_USER_AGENT


def _ensure_playwright():
    """Lazily import Playwright, raising a clear error if missing."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is required for PDF download. "
            "Install it with: pip install 'findata[server]' && python -m playwright install chromium"
        )


def _make_context(browser):
    """Create a browser context with SEC-compliant headers."""
    return browser.new_context(
        user_agent=SEC_USER_AGENT,
        extra_http_headers={
            "User-Agent": SEC_USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
    )


def _pdf_filename_from_url(url: str, index: int) -> str:
    """Derive a human-readable PDF filename from a SEC URL.

    Examples:
        ".../aapl-20240928.htm"  → "aapl-20240928.pdf"
        ".../000032019324000123" → "000032019324000123.pdf"
        (unparseable)           → "filing_001.pdf"
    """
    path = unquote(urlparse(url).path)
    basename = Path(path).stem  # strip extension (.htm, .html, etc.)
    if basename:
        # Sanitize: keep only alphanumerics, hyphens, underscores, dots
        safe = re.sub(r'[^\w\-.]', '_', basename)
        return f"{safe}.pdf"
    return f"filing_{index + 1:03d}.pdf"


def _render_single(page, url: str, page_format: str, wait_ms: int) -> bytes:
    """Navigate to *url* and return the rendered PDF bytes."""
    page.goto(url)
    page.wait_for_timeout(wait_ms)
    return page.pdf(format=page_format)


def download_filing_pdf(
    url: str | list[str],
    output_path: str | Path | None = None,
    page_format: str = "A4",
    wait_ms: int = 1500,
) -> bytes:
    """Render one or more SEC filing pages to PDF via headless Chromium.

    This is the library equivalent of the server's
    ``GET /v1/api/download-pdf`` endpoint.

    - **Single URL** (``str``): returns raw PDF bytes.
    - **Multiple URLs** (``list[str]``): renders each URL to a separate
      PDF, bundles them into an in-memory ZIP archive, and returns the
      ZIP bytes.  Filenames inside the ZIP are derived from each URL's
      path (e.g. ``aapl-20240928.pdf``).

    The browser is launched **once** and reused across all URLs for
    efficiency.

    Args:
        url:          A single URL string, or a list of URL strings.
        output_path:  If given, write the result (PDF or ZIP) to this
                      file path. Parent directories are created
                      automatically.
        page_format:  PDF page format (default ``"A4"``).
                      Other values: ``"Letter"``, ``"Legal"``, etc.
        wait_ms:      Milliseconds to wait after each page load before
                      generating the PDF (default ``1500``).

    Returns:
        Raw PDF bytes (single URL) or ZIP bytes (multiple URLs).
        Also written to *output_path* if provided.

    Raises:
        RuntimeError:  If Playwright is not installed.
        ValueError:    If *url* is an empty list.
        Exception:     Propagates any Playwright/browser errors.
    """
    sync_playwright = _ensure_playwright()

    urls = [url] if isinstance(url, str) else list(url)
    if not urls:
        raise ValueError("At least one URL is required.")

    single = len(urls) == 1

    def _run_playwright_logic():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = _make_context(browser)
            page = context.new_page()

            if single:
                result_bytes = _render_single(page, urls[0], page_format, wait_ms)
            else:
                buf = io.BytesIO()
                seen_names: dict[str, int] = {}
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, u in enumerate(urls):
                        pdf_bytes = _render_single(page, u, page_format, wait_ms)
                        name = _pdf_filename_from_url(u, i)
                        if name in seen_names:
                            seen_names[name] += 1
                            stem, ext = name.rsplit(".", 1)
                            name = f"{stem}_{seen_names[name]}.{ext}"
                        else:
                            seen_names[name] = 0
                        zf.writestr(name, pdf_bytes)
                result_bytes = buf.getvalue()

            browser.close()
            return result_bytes

    # Jupyter Notebook 등 이미 이벤트 루프가 돌고 있는 환경에서 Playwright Sync API를 
    # 호출하면 발생하는 에러를 방지하기 위해, 루프가 감지되면 별도 스레드에서 실행합니다.
    import asyncio
    import concurrent.futures

    try:
        loop = asyncio.get_running_loop()
        is_running = True
    except RuntimeError:
        is_running = False

    if is_running:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_playwright_logic)
            result_bytes = future.result()
    else:
        result_bytes = _run_playwright_logic()

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(result_bytes)

    return result_bytes


def download_filing_pdf_for(
    ticker: str,
    form_type: str = "10-K",
    date_from: str | None = None,
    date_to: str | None = None,
    output_path: str | Path | None = None,
    page_format: str = "A4",
    wait_ms: int = 1500,
    include_archive: bool | None = None,
) -> bytes:
    """Download SEC filing PDF(s) by ticker + form + date window.

    The URL-free counterpart to :func:`download_filing_pdf`: instead of a raw
    SEC URL (which you'd have to build from a CIK + accession + primary-document
    filename), you give what you actually know — the ticker, the form type, and
    an optional date range — and this resolves the matching filings' primary
    documents (via :func:`findata.find_filings`) and renders them.

    Selection:
        - No date window          → the single most recent filing → PDF bytes.
        - ``date_from``/``date_to`` → every filing in the window. One match
          returns PDF bytes; multiple matches return ZIP bytes (one PDF each).

    Args:
        ticker:          Stock symbol (e.g. ``"AAPL"``).
        form_type:       Form type to resolve (default ``"10-K"``). Comma-
                         separated values are allowed (e.g. ``"10-K,10-Q"``).
        date_from:       Inclusive lower bound, ``"YYYY-MM-DD"`` (optional).
        date_to:         Inclusive upper bound, ``"YYYY-MM-DD"`` (optional).
        output_path:     If given, also write the PDF/ZIP to this path.
        page_format:     PDF page format (default ``"A4"``).
        wait_ms:         Milliseconds to wait after each page load.
        include_archive: Walk older archive shards. Defaults to ``True`` when a
                         date window is given, else ``False``.

    Returns:
        Raw PDF bytes (one match) or ZIP bytes (multiple matches).

    Raises:
        RuntimeError: If Playwright is not installed.
        ValueError:   If the ticker is unknown, or no filing matches.
    """
    from findata.sec.filings import find_filings

    # No date window → just the latest filing. Windowed → everything in range
    # (find_filings ignores `count` when a window is given).
    rows = find_filings(
        ticker,
        form_type=form_type,
        date_from=date_from,
        date_to=date_to,
        count=1,
        include_archive=include_archive,
    )
    urls = [r["document_url"] for r in rows if r.get("document_url")]
    if not urls:
        raise ValueError(
            f"No {form_type} filing found for {ticker!r} "
            f"(date_from={date_from}, date_to={date_to})."
        )

    return download_filing_pdf(
        urls,
        output_path=output_path,
        page_format=page_format,
        wait_ms=wait_ms,
    )
