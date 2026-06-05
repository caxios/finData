"""
LangGraph state definition for the multi-agent analysis pipeline.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from operator import add

from .schemas import BusinessReport, FinancialReport, InvestmentMemo, SentimentReport


class CompanyData(TypedDict):
    """Raw data pre-fetched from the local SQLite stores, ready for prompt injection."""

    ticker: str
    cik: str | None
    company_name: str | None
    financial_inputs: dict[str, Any]
    business_inputs: dict[str, Any]
    sentiment_inputs: dict[str, Any]


class AnalysisState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes."""

    ticker: str
    company_data: CompanyData
    financial_report: FinancialReport | None
    business_report: BusinessReport | None
    sentiment_report: SentimentReport | None
    final_memo: InvestmentMemo | None
    # Errors are appended from any node — use `add` reducer so parallel writes merge.
    errors: Annotated[list[str], add]
