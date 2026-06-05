"""
CLI entry point.

Usage:
  python -m backend.agents.run_analysis --ticker AAPL
                                        [--max-chars 80000]
                                        [--no-save]
"""

from __future__ import annotations

import argparse
import json
import sys

from .data_loader import load_company_data
from .graph import build_graph
from .persistence import save_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the 4-agent investment-analysis pipeline for a single ticker."
    )
    parser.add_argument("--ticker", required=True, help="Stock symbol, e.g. AAPL")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=80_000,
        help="Per-section truncation budget for long text (default: 80000).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip writing to analysis.db / JSON file; print only.",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()

    # ── 1. Pre-fetch data ──
    print(f"[1/3] Loading data for {ticker} ...", file=sys.stderr, flush=True)
    company_data = load_company_data(ticker, max_chars=args.max_chars)

    if company_data.get("_missing"):
        print(f"  WARN top-level: {company_data['_missing']}", file=sys.stderr)
    for slot in ("financial_inputs", "business_inputs", "sentiment_inputs"):
        miss = company_data[slot].get("_missing", [])
        if miss:
            print(f"  WARN {slot}: {miss}", file=sys.stderr)

    # ── 2. Run graph ──
    print(f"[2/3] Running multi-agent graph ...", file=sys.stderr, flush=True)
    graph = build_graph()
    final_state = graph.invoke(
        {
            "ticker": ticker,
            "company_data": company_data,
            "errors": [],
        }
    )

    memo = final_state.get("final_memo")
    if memo is None:
        print("ERROR: CIO did not produce a memo. Errors:", file=sys.stderr)
        for e in final_state.get("errors", []):
            print(f"  - {e}", file=sys.stderr)
        return 1

    memo_dict = memo.model_dump()
    sub_reports = {
        "financial_report": (
            final_state["financial_report"].model_dump()
            if final_state.get("financial_report")
            else None
        ),
        "business_report": (
            final_state["business_report"].model_dump()
            if final_state.get("business_report")
            else None
        ),
        "sentiment_report": (
            final_state["sentiment_report"].model_dump()
            if final_state.get("sentiment_report")
            else None
        ),
        "errors": final_state.get("errors", []),
    }

    # ── 3. Persist ──
    if not args.no_save:
        print(f"[3/3] Saving run ...", file=sys.stderr, flush=True)
        json_path, row_id = save_run(ticker, memo_dict, sub_reports)
        print(f"  → {json_path}", file=sys.stderr)
        print(f"  → analysis.db row id={row_id}", file=sys.stderr)
    else:
        print(f"[3/3] --no-save set; skipping persistence.", file=sys.stderr, flush=True)

    # ── stdout: the structured memo + Markdown ──
    # Remove the massive markdown string from the JSON print so it doesn't duplicate
    display_dict = memo_dict.copy()
    markdown_text = display_dict.pop("memo_markdown", "")
    
    print(json.dumps(display_dict, indent=2, default=str))
    print("\n" + "=" * 80)
    print(markdown_text)
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
