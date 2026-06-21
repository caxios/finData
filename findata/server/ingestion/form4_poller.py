"""
Form 4 market-wide realtime polling worker (plan 04).

Continuously captures every company's newest Form 4 filings so the API can
serve near-realtime insider-trading data, at low cost. Designed to run as a
process **separate from the API server** (the worker writes; the API reads).

Two jobs:
- ``run_market_poll()``        — every ~10 min: latest ~100 Form 4s (getcurrent
                                  Atom feed) → dedup-save. Cost is bounded by the
                                  number of *new* filings, not the poll frequency.
- ``reconcile_daily_index()``  — once/day: EDGAR daily master index → catch any
                                  Form 4s that rolled off the 100-entry feed during
                                  high-volume periods.

Usage::

    # single poll cycle, then exit
    python -m findata.server.ingestion.form4_poller

    # run continuously, polling every 600s (with daily reconciliation)
    python -m findata.server.ingestion.form4_poller --loop 600

    # one-off daily reconciliation for a given date
    python -m findata.server.ingestion.form4_poller --reconcile --date 2026-06-20

Cost note: the poll itself is ~free (one GET / cycle). The real cost is parsing
*new* filings, which dedup (``save_to_db``) minimizes. Don't lower the poll
frequency to save money — keep the cadence and rely on dedup.
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime, timezone

import requests

from findata.sec.const import SEC_USER_AGENT
from findata.sec.utils.form4.form4_parser import parse_all_from_rss, parse_form4
from findata.server.db.config import INSIDER_ALL_DB
from findata.server.db.form4_db import save_to_db

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────
DEFAULT_POLL_INTERVAL = 600        # 10 minutes
DEFAULT_RECONCILE_INTERVAL = 86_400  # 24 hours
FANOUT_DELAY = 0.2                  # seconds between per-filing fetches (SEC etiquette)

_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


# ── Observability: last-run status ──────────────────────────────────
_status_lock = threading.Lock()
_last_run: dict = {
    "last_poll_ts": None,
    "last_success_ts": None,
    "last_inserted": None,
    "last_skipped": None,
    "last_error": None,
    "consecutive_failures": 0,
    "total_polls": 0,
}


def get_poller_status() -> dict:
    """Return a snapshot of the poller's last-run state (for health checks)."""
    with _status_lock:
        return dict(_last_run)


def _record_poll(*, ok: bool, inserted: int = 0, skipped: int = 0,
                 error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _status_lock:
        _last_run["last_poll_ts"] = now
        _last_run["total_polls"] += 1
        if ok:
            _last_run["last_success_ts"] = now
            _last_run["last_inserted"] = inserted
            _last_run["last_skipped"] = skipped
            _last_run["last_error"] = None
            _last_run["consecutive_failures"] = 0
        else:
            _last_run["last_error"] = error
            _last_run["consecutive_failures"] += 1


# ── Job 1: market-wide poll ─────────────────────────────────────────

def run_market_poll(db_path: str = INSIDER_ALL_DB) -> tuple[int, int]:
    """One poll cycle: fetch latest ~100 Form 4s and dedup-save.

    Returns ``(inserted, skipped)``. Never raises — failures are logged and
    recorded so a long-running loop survives transient network errors.
    """
    try:
        filings = parse_all_from_rss()
        inserted, skipped = save_to_db(filings, db_path)
        _record_poll(ok=True, inserted=inserted, skipped=skipped)
        logger.info("form4 market poll: %d inserted, %d skipped", inserted, skipped)
        return inserted, skipped
    except Exception as e:  # noqa: BLE001 — worker must not crash on a bad cycle
        _record_poll(ok=False, error=repr(e))
        logger.exception("form4 market poll failed: %s", e)
        return 0, 0


# ── Job 2: daily index reconciliation ───────────────────────────────

def _daily_master_index_url(d: datetime) -> str:
    """EDGAR daily master index URL for a date (pipe-delimited)."""
    quarter = (d.month - 1) // 3 + 1
    yyyymmdd = d.strftime("%Y%m%d")
    return (
        f"https://www.sec.gov/Archives/edgar/daily-index/"
        f"{d.year}/QTR{quarter}/master.{yyyymmdd}.idx"
    )


def _parse_master_idx_for_form4(text: str) -> list[str]:
    """Extract full .txt submission URLs for Form 4 / 4/A from a master.idx body.

    master.idx rows: ``CIK|Company Name|Form Type|Date Filed|File Name``
    (File Name is a path like ``edgar/data/<cik>/<accession>.txt``).
    """
    urls: list[str] = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) != 5:
            continue  # header/description lines
        form_type = parts[2].strip()
        if form_type not in ("4", "4/A"):
            continue
        file_name = parts[4].strip()
        if not file_name.endswith(".txt"):
            continue
        urls.append(f"https://www.sec.gov/Archives/{file_name}")
    return urls


def reconcile_daily_index(
    date: datetime | str | None = None,
    db_path: str = INSIDER_ALL_DB,
    *,
    limit: int | None = None,
    delay: float = FANOUT_DELAY,
) -> tuple[int, int]:
    """Backfill Form 4s from EDGAR's daily master index for ``date``.

    Catches filings that rolled off the 100-entry ``getcurrent`` feed during
    high-volume periods. dedup (``save_to_db``) makes re-runs safe.

    Args:
        date:   The day to reconcile (datetime or 'YYYY-MM-DD'); defaults to
                today (UTC).
        limit:  Optional cap on filings to process (testing / safety).
        delay:  Seconds between per-filing fetches (SEC fair-access).

    Returns ``(inserted, skipped)``.
    """
    if date is None:
        d = datetime.now(timezone.utc)
    elif isinstance(date, str):
        d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        d = date

    url = _daily_master_index_url(d)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
    except Exception as e:  # noqa: BLE001
        logger.warning("daily index fetch error for %s: %s", url, e)
        return 0, 0

    if resp.status_code == 404:
        # No index for this date (weekend/holiday) — not an error.
        logger.info("no daily index for %s (404) — skipping", d.strftime("%Y-%m-%d"))
        return 0, 0
    if not resp.ok:
        logger.warning("daily index %s returned HTTP %d", url, resp.status_code)
        return 0, 0

    filing_urls = _parse_master_idx_for_form4(resp.text)
    if limit is not None:
        filing_urls = filing_urls[:limit]
    logger.info("daily index %s: %d Form 4 filings", d.strftime("%Y-%m-%d"), len(filing_urls))

    parsed: list[dict] = []
    for furl in filing_urls:
        try:
            parsed.append(parse_form4(furl))
        except Exception as e:  # noqa: BLE001 — skip individual bad filings
            logger.warning("failed to parse %s: %s", furl, e)
        time.sleep(delay)

    if not parsed:
        return 0, 0
    inserted, skipped = save_to_db(parsed, db_path)
    logger.info("daily reconciliation: %d inserted, %d skipped", inserted, skipped)
    return inserted, skipped


# ── Scheduler: in-process background loop ───────────────────────────

def run_loop(
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    reconcile_interval: int = DEFAULT_RECONCILE_INTERVAL,
    db_path: str = INSIDER_ALL_DB,
    *,
    stop_event: threading.Event | None = None,
) -> None:
    """Run the poll cycle every ``poll_interval`` seconds until stopped.

    Runs ``reconcile_daily_index`` roughly every ``reconcile_interval`` seconds.
    Blocking; call from a dedicated thread/process. Pass a ``stop_event`` to
    request a clean shutdown.
    """
    stop = stop_event or threading.Event()
    last_reconcile = 0.0
    logger.info("form4 poller loop started (poll=%ss, reconcile=%ss)",
                poll_interval, reconcile_interval)
    while not stop.is_set():
        run_market_poll(db_path)
        now = time.monotonic()
        if now - last_reconcile >= reconcile_interval:
            try:
                reconcile_daily_index(db_path=db_path)
            except Exception as e:  # noqa: BLE001
                logger.exception("daily reconciliation failed: %s", e)
            last_reconcile = now
        stop.wait(poll_interval)
    logger.info("form4 poller loop stopped")


def start_background_poller(
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    reconcile_interval: int = DEFAULT_RECONCILE_INTERVAL,
    db_path: str = INSIDER_ALL_DB,
) -> threading.Event:
    """Start the poll loop on a daemon thread. Returns the stop Event.

    Used by the API process when ``ENABLE_FORM4_POLLER=1`` (single-instance
    MVP). For multi-instance deployments run the worker separately
    (EventBridge+Lambda / ECS scheduled task) — see 08_deployment_and_infra.md.
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_loop,
        kwargs={
            "poll_interval": poll_interval,
            "reconcile_interval": reconcile_interval,
            "db_path": db_path,
            "stop_event": stop_event,
        },
        name="form4-poller",
        daemon=True,
    )
    thread.start()
    return stop_event


# ── CLI entrypoint ──────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Form 4 market-wide polling worker")
    parser.add_argument(
        "--loop", type=int, metavar="SECONDS",
        help="Run continuously, polling every SECONDS (e.g. 600). "
             "Omit for a single poll cycle.",
    )
    parser.add_argument(
        "--reconcile", action="store_true",
        help="Run a one-off daily-index reconciliation and exit.",
    )
    parser.add_argument(
        "--date", type=str, metavar="YYYY-MM-DD",
        help="Date for --reconcile (default: today UTC).",
    )
    parser.add_argument(
        "--reconcile-interval", type=int, default=DEFAULT_RECONCILE_INTERVAL,
        help="Seconds between reconciliations in --loop mode (default: 86400).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.reconcile:
        reconcile_daily_index(date=args.date)
        return

    if args.loop:
        run_loop(poll_interval=args.loop, reconcile_interval=args.reconcile_interval)
        return

    # Default: a single poll cycle.
    run_market_poll()


if __name__ == "__main__":
    main()
