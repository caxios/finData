"""
Throttling helpers for scheduled ingestion (plan 06 §3.4 / Step 3).

Pure, dependency-free utilities so large universe runs stay under provider
rate limits (notably OpenDART's daily request cap):
- ``chunked``         — split a universe into batches so a run can be spread out.
- ``run_with_backoff`` — retry a call with exponential backoff on (quota) errors.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def chunked(seq: Sequence[T], size: int) -> Iterator[list[T]]:
    """Yield successive ``size``-length chunks of ``seq``.

    ``size <= 0`` yields the whole sequence as one chunk.
    """
    items = list(seq)
    if size <= 0:
        if items:
            yield items
        return
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_with_backoff(
    fn: Callable[[], R],
    *,
    retries: int = 3,
    base_delay: float = 2.0,
    is_retryable: Callable[[Exception], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> R:
    """Call ``fn``; on a retryable error, retry with exponential backoff.

    Args:
        retries:      Max retries after the first attempt.
        base_delay:   Base seconds; delay = base_delay * 2**(attempt-1).
        is_retryable: Predicate deciding if an exception should be retried.
                      If None, every exception is retried (up to ``retries``).
        sleep:        Injectable sleep (for testing).

    Re-raises the last exception if retries are exhausted or the error is not
    retryable.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — caller decides via is_retryable
            if is_retryable is not None and not is_retryable(e):
                raise
            attempt += 1
            if attempt > retries:
                raise
            sleep(base_delay * (2 ** (attempt - 1)))
