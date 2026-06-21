"""
One-time universe warm-up (plan 06 Step 6 / referenced by 08 deploy step 7).

On first deploy, populate storage for the data universe so the first users don't
trigger a stampede of on-demand fetches (which could hit EDGAR/DART rate limits).
Idempotent — ``save_batch`` / ``save_to_db`` dedupe, so it's safe to re-run.

Usage::

    python -m findata.server.ingestion.warmup            # warm US + KR
    python -m findata.server.ingestion.warmup --kr-only
    python -m findata.server.ingestion.warmup --us-only --count 10
"""

from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)


def run_warmup(
    universe_us: list[str] | None = None,
    universe_kr: list[str] | None = None,
    *,
    count: int = 5,
    include_us: bool = True,
    include_kr: bool = True,
) -> dict:
    """Pre-warm the universe (US 10-K/Q + KR DART). Returns a summary dict.

    Lazy imports keep this usable even when DART deps are absent (KR is skipped).
    """
    summary: dict = {"us": None, "kr": None}

    if include_us:
        try:
            from findata.server.ingestion.sec_10kq_ingest import run_10kq_refresh
            run_10kq_refresh(universe=universe_us, count=count)
            summary["us"] = "ok"
            logger.info("warm-up: US 10-K/Q complete")
        except Exception as e:  # noqa: BLE001
            summary["us"] = f"error: {e!r}"
            logger.exception("warm-up: US 10-K/Q failed: %s", e)

    if include_kr:
        try:
            from findata.server.ingestion.dart_batch import run_dart_refresh
            summary["kr"] = run_dart_refresh(universe=universe_kr)
            logger.info("warm-up: KR DART complete")
        except ModuleNotFoundError as e:
            summary["kr"] = f"skipped (deps missing): {e!r}"
            logger.warning("warm-up: KR DART skipped (deps missing): %s", e)
        except Exception as e:  # noqa: BLE001
            summary["kr"] = f"error: {e!r}"
            logger.exception("warm-up: KR DART failed: %s", e)

    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="One-time universe warm-up")
    parser.add_argument("--us-only", action="store_true", help="Warm only US (SEC).")
    parser.add_argument("--kr-only", action="store_true", help="Warm only KR (DART).")
    parser.add_argument("--count", type=int, default=5, help="Filings per US company.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    include_us = not args.kr_only
    include_kr = not args.us_only
    result = run_warmup(count=args.count, include_us=include_us, include_kr=include_kr)
    logger.info("warm-up summary: %s", result)


if __name__ == "__main__":
    main()
