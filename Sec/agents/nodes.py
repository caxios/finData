"""
The four agent nodes used by the LangGraph pipeline.

Each analyst node receives the full state, pulls only its slice of inputs from
`state["company_data"]`, calls Gemini with a structured-output schema, and writes
its report back into state.
"""

from __future__ import annotations

import json
import sys
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .prompts import (
    BUSINESS_RISK_AGENT_PROMPT,
    CIO_AGENT_PROMPT,
    FINANCIAL_AGENT_PROMPT,
    SENTIMENT_AGENT_PROMPT,
)
from .schemas import (
    BusinessReport,
    FinancialReport,
    InvestmentMemo,
    SentimentReport,
)
from .state import AnalysisState


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _invoke_structured(system_prompt: str, payload: dict, schema, *, temperature: float = 0.2):
    llm = get_llm(temperature=temperature)
    structured = llm.with_structured_output(schema)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                "Below is the JSON payload of inputs you may consider. "
                "Respond ONLY with a JSON object matching the required schema.\n\n"
                f"```json\n{json.dumps(payload, indent=2, default=str)}\n```"
            )
        ),
    ]
    return structured.invoke(messages)


# ── Analyst nodes ─────────────────────────────────────────────────────
def financial_node(state: AnalysisState) -> dict:
    _log("→ financial agent: starting")
    try:
        report = _invoke_structured(
            FINANCIAL_AGENT_PROMPT,
            state["company_data"]["financial_inputs"],
            FinancialReport,
        )
        _log("✓ financial agent: done")
        return {"financial_report": report}
    except Exception as e:
        _log(f"✗ financial agent: {e!r}")
        return {"errors": [f"financial: {e!r}"], "financial_report": None}


def business_node(state: AnalysisState) -> dict:
    _log("→ business/risk agent: starting")
    try:
        report = _invoke_structured(
            BUSINESS_RISK_AGENT_PROMPT,
            state["company_data"]["business_inputs"],
            BusinessReport,
        )
        _log("✓ business/risk agent: done")
        return {"business_report": report}
    except Exception as e:
        _log(f"✗ business/risk agent: {e!r}")
        return {"errors": [f"business: {e!r}"], "business_report": None}


def sentiment_node(state: AnalysisState) -> dict:
    _log("→ sentiment agent: starting")
    try:
        report = _invoke_structured(
            SENTIMENT_AGENT_PROMPT,
            state["company_data"]["sentiment_inputs"],
            SentimentReport,
        )
        _log("✓ sentiment agent: done")
        return {"sentiment_report": report}
    except Exception as e:
        _log(f"✗ sentiment agent: {e!r}")
        return {"errors": [f"sentiment: {e!r}"], "sentiment_report": None}


# ── CIO synthesis node ────────────────────────────────────────────────
def cio_node(state: AnalysisState) -> dict:
    _log("→ CIO agent: synthesizing")
    ticker = state["ticker"]

    payload = {
        "ticker": ticker,
        "as_of": date.today().isoformat(),
        "financial_report": (
            state["financial_report"].model_dump() if state.get("financial_report") else None
        ),
        "business_report": (
            state["business_report"].model_dump() if state.get("business_report") else None
        ),
        "sentiment_report": (
            state["sentiment_report"].model_dump() if state.get("sentiment_report") else None
        ),
        "errors_from_subordinates": state.get("errors", []),
    }

    try:
        memo = _invoke_structured(
            CIO_AGENT_PROMPT,
            payload,
            InvestmentMemo,
            temperature=0.3,
        )
        _log("✓ CIO agent: done")
        return {"final_memo": memo}
    except Exception as e:
        _log(f"✗ CIO agent: {e!r}")
        return {"errors": [f"cio: {e!r}"], "final_memo": None}
