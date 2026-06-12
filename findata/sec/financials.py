"""
SEC XBRL financial facts — library layer.

Fetches XBRL company facts from SEC EDGAR and returns ``list[dict]``
in memory. Nothing is saved to disk.

Usage::

    import findata

    facts = findata.get_financials("AAPL")
"""

from __future__ import annotations

from typing import Any

from findata.sec._cik import lookup_cik
from findata.sec.company_facts.company_specific_fin import get_company_facts


def get_financials(ticker: str) -> list[dict[str, Any]]:
    """Fetch XBRL financial facts from SEC's companyfacts API.

    Returns a flat ``list[dict]`` where each dict represents one XBRL
    observation (concept, value, period, filing, etc.).
    Nothing is written to disk.

    Args:
        ticker: Stock symbol (e.g. ``"AAPL"``).

    Returns:
        List of fact dicts with keys: taxonomy, concept, label, unit,
        period_start, period_end, val, accn, fy, fp, form, filed, frame.

    Raises:
        ValueError: If the ticker cannot be resolved to a CIK or
                    no facts are available.
    """
    cik, _ = lookup_cik(ticker)
    if not cik:
        raise ValueError(f"Unknown ticker: {ticker}")

    facts_json = get_company_facts(ticker)
    if not facts_json:
        raise ValueError(f"No financial facts found for {ticker}")

    rows: list[dict[str, Any]] = []
    cik_padded = str(facts_json.get("cik", cik)).zfill(10)

    for taxonomy, concepts in facts_json.get("facts", {}).items():
        for concept, payload in concepts.items():
            label = payload.get("label")
            for unit, observations in payload.get("units", {}).items():
                for obs in observations:
                    if "end" not in obs or "val" not in obs:
                        continue
                    rows.append({
                        "cik": cik_padded,
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "label": label,
                        "unit": unit,
                        "period_start": obs.get("start"),
                        "period_end": obs["end"],
                        "val": obs["val"],
                        "accn": obs.get("accn"),
                        "fy": obs.get("fy"),
                        "fp": obs.get("fp"),
                        "form": obs.get("form"),
                        "filed": obs.get("filed"),
                        "frame": obs.get("frame"),
                    })

    return rows
