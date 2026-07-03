"""
One-time universe warm-up (plan 06 Step 6 / referenced by 08 deploy step 7).

On first deploy, populate storage for the data universe so the first users don't
trigger a stampede of on-demand fetches (which could hit EDGAR rate limits).
Idempotent — ``save_batch`` dedupes, so it's safe to re-run.

Usage::

    python -m findata.server.ingestion.warmup            # warm US universe
    python -m findata.server.ingestion.warmup --count 10
"""

from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)


def run_warmup(
    universe_us: list[str] | None = None,
    *,
    count: int = 5,
) -> dict:
    """Pre-warm the US 10-K/Q universe. Returns a summary dict."""
    summary: dict = {"us": None}

    try:
        from findata.server.ingestion.sec_10kq_ingest import run_10kq_refresh
        run_10kq_refresh(universe=universe_us, count=count)
        summary["us"] = "ok"
        logger.info("warm-up: US 10-K/Q complete")
    except Exception as e:  # noqa: BLE001
        summary["us"] = f"error: {e!r}"
        logger.exception("warm-up: US 10-K/Q failed: %s", e)

    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="One-time universe warm-up")
    parser.add_argument("--count", type=int, default=5, help="Filings per company.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    result = run_warmup(count=args.count)
    logger.info("warm-up summary: %s", result)


if __name__ == "__main__":
    main()
