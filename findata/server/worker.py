"""
Background worker entrypoint (plan 08 Step 6).

Runs the ingestion jobs in a process **separate from the API** so fetch load
never affects request latency, and so only ONE process polls (avoiding
duplicate ingestion / write contention):

- Form 4 market-wide poller (plan 04) — every ~10 min, foreground loop.
- Scheduled 10-K/Q refresh (plan 06) — daily, background thread.

This is the container command for the *worker* role:

    python -m findata.server.worker

The API container does NOT run this; its in-process schedulers stay gated off
(ENABLE_FORM4_POLLER / ENABLE_SCHEDULED_INGESTION unset). The worker runs the
jobs unconditionally because running them *is* its job.

Intervals can be tuned via env: FORM4_POLL_INTERVAL, SCHED_10KQ_INTERVAL
(seconds).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from findata.server.db.config import ensure_data_dirs
    from findata.server.ingestion.form4_poller import (
        run_loop as poller_loop,
        DEFAULT_POLL_INTERVAL,
        DEFAULT_RECONCILE_INTERVAL,
    )
    from findata.server.ingestion.scheduled import (
        start_background_scheduler,
        DEFAULT_10KQ_INTERVAL,
    )

    ensure_data_dirs()

    poll_interval = int(os.getenv("FORM4_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL)))
    kq_interval = int(os.getenv("SCHED_10KQ_INTERVAL", str(DEFAULT_10KQ_INTERVAL)))

    logger.info("worker starting: form4 poll=%ss, 10kq=%ss",
                poll_interval, kq_interval)

    # Daily 10-K/Q refresh on a background thread …
    start_background_scheduler(kq_interval=kq_interval)
    # … and the Form 4 poller in the foreground (blocks until the process exits).
    poller_loop(poll_interval=poll_interval,
                reconcile_interval=DEFAULT_RECONCILE_INTERVAL)


if __name__ == "__main__":
    main()
