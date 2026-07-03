"""
Scheduled ingestion worker (plan 06 Step 4).

Runs the 10-K/Q refresher on a recurring cadence, in a process **separate from
the API** (or, for the single-instance MVP, on a gated daemon thread). Mirrors
the Form 4 poller (plan 04): gated behind an env flag so only ONE process runs
it (running it everywhere would double-ingest).

Cadence (plan 06 §3.2): a *daily* check is right even though filings are
immutable — new ones drop on irregular dates, and dedup keeps a daily run cheap.

Usage::

    # single refresh cycle, then exit
    python -m findata.server.ingestion.scheduled --once

    # run continuously (10-K/Q daily)
    python -m findata.server.ingestion.scheduled --loop
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────
DEFAULT_10KQ_INTERVAL = 86_400      # daily

# ── Observability ───────────────────────────────────────────────────
_status_lock = threading.Lock()
_status: dict = {
    "last_10kq_ts": None,
    "last_error": None,
    "total_cycles": 0,
}


def get_scheduler_status() -> dict:
    with _status_lock:
        return dict(_status)


def _mark(field: str, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _status_lock:
        if field:
            _status[field] = now
        if error is not None:
            _status["last_error"] = error


# ── Jobs ────────────────────────────────────────────────────────────

def refresh_10kq(count: int = 5) -> None:
    """Run the 10-K/Q refresh for the universe. Never raises."""
    try:
        from findata.server.ingestion.sec_10kq_ingest import run_10kq_refresh
        run_10kq_refresh(count=count)
        _mark("last_10kq_ts")
        logger.info("scheduled 10-K/Q refresh complete")
    except Exception as e:  # noqa: BLE001 — worker must survive a bad cycle
        _mark("", error=f"10kq: {e!r}")
        logger.exception("scheduled 10-K/Q refresh failed: %s", e)


def run_once(count: int = 5) -> None:
    """Run one refresh cycle."""
    refresh_10kq(count=count)
    with _status_lock:
        _status["total_cycles"] += 1


# ── Loop / background thread ────────────────────────────────────────

def run_loop(
    kq_interval: int = DEFAULT_10KQ_INTERVAL,
    count: int = 5,
    *,
    stop_event: threading.Event | None = None,
    tick: int = 60,
) -> None:
    """Run 10-K/Q every ``kq_interval`` seconds."""
    stop = stop_event or threading.Event()
    last_kq = 0.0
    logger.info("scheduled ingestion loop started (10kq=%ss)", kq_interval)
    while not stop.is_set():
        now = time.monotonic()
        if now - last_kq >= kq_interval:
            refresh_10kq(count=count)
            last_kq = now
        with _status_lock:
            _status["total_cycles"] += 1
        stop.wait(tick)
    logger.info("scheduled ingestion loop stopped")


def start_background_scheduler(
    kq_interval: int = DEFAULT_10KQ_INTERVAL,
    count: int = 5,
) -> threading.Event:
    """Start the scheduled-ingestion loop on a daemon thread; return stop Event."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_loop,
        kwargs={"kq_interval": kq_interval, "count": count, "stop_event": stop_event},
        name="scheduled-ingestion",
        daemon=True,
    )
    thread.start()
    return stop_event


# ── CLI ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scheduled 10-K/Q ingestion")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--count", type=int, default=5, help="Filings per company.")
    parser.add_argument("--kq-interval", type=int, default=DEFAULT_10KQ_INTERVAL)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.loop:
        run_loop(args.kq_interval, count=args.count)
    else:
        run_once(count=args.count)


if __name__ == "__main__":
    main()
