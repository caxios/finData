"""
Subprocess worker for PDF rendering.

Run as::

    python -m findata.sec._pdf_worker <spec.json>

``download_filing_pdf`` spawns this in a fresh process so Playwright's *sync*
browser starts reliably from any host. Notebook kernels (Jupyter/IPython) and
other asyncio/Tornado hosts leave the parent process's event-loop policy in a
state where the browser fails to launch — on Windows as ``WinError 10014`` /
"no running event loop". A clean child process has none of that: it sets the
Proactor policy (required by Playwright on Windows) and renders like a plain
script.

Protocol:
    - argv[1] is a JSON spec file: ``{urls, page_format, wait_ms, out_path}``.
    - On success: writes the PDF/ZIP bytes to ``out_path`` and exits 0.
    - On SEC rate-limit block: writes the message to stderr and exits with
      ``_WORKER_BLOCKED_CODE`` so the parent re-raises ``SECAccessBlocked``.
    - On any other error: exits non-zero with the traceback on stderr.
"""

from __future__ import annotations

import asyncio
import json
import sys


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python -m findata.sec._pdf_worker <spec.json>\n")
        return 2

    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)

    # Windows: Playwright requires the Proactor event loop. Set it before the
    # render path touches asyncio (the parent may have run under a Selector
    # policy installed by Jupyter/Tornado).
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Imported here (after the policy is set) to keep import side effects inside
    # the configured process.
    from findata.sec.pdf import _WORKER_BLOCKED_CODE, SECAccessBlocked, _render_urls

    try:
        data = _render_urls(spec["urls"], spec["page_format"], spec["wait_ms"])
    except SECAccessBlocked as e:
        sys.stderr.write(str(e))
        return _WORKER_BLOCKED_CODE

    with open(spec["out_path"], "wb") as f:
        f.write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
