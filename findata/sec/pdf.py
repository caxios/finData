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
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

from findata.sec.const import HEADERS, SEC_USER_AGENT

# Exit code the subprocess worker uses to signal a SEC rate-limit block, so the
# parent can re-raise SECAccessBlocked instead of a generic RuntimeError.
_WORKER_BLOCKED_CODE = 3

# Project root (the dir containing the ``findata`` package) — passed to the
# render subprocess on PYTHONPATH so it can import findata no matter what its
# working directory is (e.g. a notebook opened from an unrelated folder).
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


class SECAccessBlocked(RuntimeError):
    """Raised when SEC serves its 'undeclared automated tool' interstitial.

    SEC's rate limiter returns an HTML block page *in place of* the filing when
    it decides traffic looks automated (usually from request volume/bursts, or
    a temporarily flagged IP). Without this, that block page would be silently
    rendered into a PDF — so we detect it and fail loudly instead.
    """


# Phrases that appear only on SEC's rate-limit interstitial, not in real
# filings. Matched against the loaded page's HTML to detect a block.
_SEC_BLOCK_MARKERS = (
    "Undeclared Automated Tool",
    "network of automated tools",
    "declare your traffic",
)



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
    """Create a browser context with SEC-compliant headers.

    Also aborts all network requests from the browser: rendering is done from
    locally-fetched HTML (set_content), so the browser should never reach out
    to sec.gov — which is what keeps SEC's automated-tool limiter from ever
    seeing browser traffic.
    """
    context = browser.new_context(
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
    # The browser renders local HTML (via set_content) and must never reach the
    # network: any http(s) sub-resource (e.g. an absolute sec.gov image URL)
    # would re-expose us to SEC's rate limiter. Abort every network request;
    # inline assets (data: URIs) and unresolved relatives are unaffected.
    context.route(
        "**/*",
        lambda route: (
            route.abort()
            if route.request.url.startswith(("http://", "https://"))
            else route.continue_()
        ),
    )
    return context


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


def _looks_blocked(html: str) -> bool:
    """True if *html* is SEC's rate-limit interstitial rather than a filing."""
    head = html[:4000]  # the block notice is at the very top of the document
    return any(marker in head for marker in _SEC_BLOCK_MARKERS)


def _fetch_filing_html(
    url: str,
    max_attempts: int = 3,
    backoff_s: float = 4.0,
) -> str:
    """Download a filing's HTML with the declared SEC User-Agent.

    We fetch with ``requests`` (not the browser) because SEC fingerprints and
    rate-limits headless Chromium far more aggressively than a plain declared
    request — the same reason ``get_filings`` fetches reliably. If SEC serves
    its automated-tool interstitial, retry with exponential backoff, then raise
    :class:`SECAccessBlocked`.
    """
    for attempt in range(max_attempts):
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        html = resp.text
        if not _looks_blocked(html):
            return html
        if attempt < max_attempts - 1:
            time.sleep(backoff_s * (2 ** attempt))

    raise SECAccessBlocked(
        "SEC returned its 'undeclared automated tool' page instead of the "
        f"filing (URL: {url}). Your traffic is temporarily rate-limited. What "
        "helps: set a descriptive FINDATA_SEC_USER_AGENT (e.g. "
        "'YourCompany you@email.com'), wait a few minutes, and avoid fetching "
        "many filings back-to-back."
    )


def _render_single(page, url: str, page_format: str, wait_ms: int) -> bytes:
    """Fetch *url*'s HTML via requests, render it locally, return PDF bytes.

    The browser renders HTML loaded with ``set_content`` — it never navigates
    to sec.gov — so SEC only ever sees the single trusted ``requests`` fetch.
    (Trade-off: images/external assets referenced by relative URLs aren't
    fetched, so the PDF is text-and-layout faithful but may omit some images.)
    """
    html = _fetch_filing_html(url)
    page.set_content(html, wait_until="domcontentloaded")
    page.wait_for_timeout(wait_ms)
    return page.pdf(format=page_format)


def _render_urls(urls: list[str], page_format: str, wait_ms: int) -> bytes:
    """Launch Chromium once, render every URL, return PDF or ZIP bytes.

    Drives the Playwright **sync** API in the current process — so the caller
    must be in an event-loop-clean context. :func:`download_filing_pdf` runs
    this inside a dedicated subprocess (via ``_pdf_worker``) precisely so that
    contract always holds, even under Jupyter/Tornado on Windows.

    Single URL → PDF bytes. Multiple URLs → ZIP bytes (one PDF per filing).
    """
    sync_playwright = _ensure_playwright()
    single = len(urls) == 1

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


def _render_urls_isolated(urls: list[str], page_format: str, wait_ms: int) -> bytes:
    """Render in a clean child process so the browser always starts.

    A headless-browser sync API needs a compatible asyncio state. Notebook
    kernels (Jupyter/IPython) and other async hosts leave the process's
    event-loop policy in a state where Playwright fails to launch — on Windows
    this surfaces as ``WinError 10014`` / "no running event loop". A fresh child
    process has none of that baggage: it sets the Proactor policy and runs the
    render exactly like a plain script.
    """
    import json
    import subprocess
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="findata_pdf_")
    spec_path = os.path.join(tmpdir, "spec.json")
    out_path = os.path.join(tmpdir, "out.bin")
    try:
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "urls": urls,
                    "page_format": page_format,
                    "wait_ms": wait_ms,
                    "out_path": out_path,
                },
                f,
            )

        # Ensure the worker can import findata regardless of its CWD.
        env = dict(os.environ)
        env["PYTHONPATH"] = (
            _PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
        ).rstrip(os.pathsep)

        proc = subprocess.run(
            [sys.executable, "-m", "findata.sec._pdf_worker", spec_path],
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode == _WORKER_BLOCKED_CODE:
            raise SECAccessBlocked(proc.stderr.strip() or "SEC blocked the request.")
        if proc.returncode != 0:
            raise RuntimeError(
                "PDF rendering failed in the worker subprocess:\n"
                + (proc.stderr.strip() or "(no error output)")
            )

        with open(out_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def download_filing_pdf(
    url: str | list[str],
    output_path: str | Path | None = None,
    page_format: str = "A4",
    wait_ms: int = 1500,
) -> bytes:
    """Render one or more SEC filings to PDF via headless Chromium.

    This is the library equivalent of the server's
    ``GET /v1/api/download-pdf`` endpoint.

    - **Single URL** (``str``): returns raw PDF bytes.
    - **Multiple URLs** (``list[str]``): renders each URL to a separate
      PDF, bundles them into an in-memory ZIP archive, and returns the
      ZIP bytes.  Filenames inside the ZIP are derived from each URL's
      path (e.g. ``aapl-20240928.pdf``).

    The rendering runs in an isolated subprocess so it works from **any** host —
    including Jupyter/IPython notebooks on Windows, where Playwright's sync
    browser otherwise fails to start due to the event-loop policy. The browser
    is launched **once** in that subprocess and reused across all URLs.

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
        RuntimeError:      If Playwright is not installed.
        ValueError:        If *url* is an empty list.
        SECAccessBlocked:  If SEC rate-limits the fetch.
    """
    urls = [url] if isinstance(url, str) else list(url)
    if not urls:
        raise ValueError("At least one URL is required.")

    result_bytes = _render_urls_isolated(urls, page_format, wait_ms)

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
