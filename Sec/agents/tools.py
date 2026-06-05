"""
Tools provisioned to the conversational CIO agent.

Two categories:
  1. SQLDatabaseToolkit on the insider-trades DB (the user referenced
     "insider_track.db"; in this repo that maps to insider_watchlist.db, with
     insider_all.db as a fallback).
  2. Sub-agent consultant tools — let the CIO ping the Financial / Risk /
     Sentiment agents on demand for focused, qualitative answers.
"""

from __future__ import annotations

import json
import os

from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from .data_loader import (
    INSIDER_ALL_DB,
    INSIDER_WATCHLIST_DB,
    load_company_data,
)
from .llm import get_llm
from .prompts import (
    BUSINESS_RISK_AGENT_PROMPT,
    FINANCIAL_AGENT_PROMPT,
    SENTIMENT_AGENT_PROMPT,
)
from .schemas import BusinessReport, FinancialReport, SentimentReport


# ── 1. SQL toolkit ────────────────────────────────────────────────────
def _pick_insider_db() -> str:
    """The user's prompt referenced 'insider_track.db'.

    In this repo the actual files are insider_watchlist.db (preferred) and
    insider_all.db (fallback); pick whichever exists. The file path can be
    overridden via the INSIDER_DB env var.
    """
    override = os.environ.get("INSIDER_DB")
    if override and os.path.exists(override):
        return override
    if os.path.exists(INSIDER_WATCHLIST_DB):
        return INSIDER_WATCHLIST_DB
    if os.path.exists(INSIDER_ALL_DB):
        return INSIDER_ALL_DB
    raise FileNotFoundError(
        "No insider trades DB found. Expected insider_watchlist.db or "
        "insider_all.db under backend/db/, or INSIDER_DB env var pointing to one."
    )


def get_sql_toolkit_tools():
    """SQLDatabaseToolkit produces 4 tools:
        sql_db_query, sql_db_schema, sql_db_list_tables, sql_db_query_checker.
    """
    db_path = _pick_insider_db()
    db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
    toolkit = SQLDatabaseToolkit(db=db, llm=get_llm())
    return toolkit.get_tools()


# ── 2. Sub-agent consultant tools ─────────────────────────────────────
def _consult(system_prompt: str, schema, ticker: str, question: str, slot: str) -> str:
    """Shared helper: load the right slice of company_data, pose a focused
    question to the relevant subordinate agent, return JSON."""
    data = load_company_data(ticker)
    payload = {
        "ticker": ticker,
        "user_question_focus": question,
        "data": data[slot],
    }
    llm = get_llm(temperature=0.2)
    structured = llm.with_structured_output(schema)
    msgs = [
        SystemMessage(
            content=(
                system_prompt
                + "\n\nThe CIO has forwarded a SPECIFIC FOLLOW-UP QUESTION from the user. "
                "Tailor your structured report so it answers that question. The question is "
                "in the `user_question_focus` field of the input.\n\n"
                "CRITICAL INSTRUCTION: You MUST ONLY use the data provided in the Input payload. "
                "The Input payload contains real data from the database files. "
                "Do NOT hallucinate or bring in outside information. "
                "If the data is not in the payload, clearly state that the data is not available in the database files."
            )
        ),
        HumanMessage(
            content=(
                "Input payload (only data — strict scope):\n"
                f"```json\n{json.dumps(payload, indent=2, default=str)}\n```"
            )
        ),
    ]
    report = structured.invoke(msgs)
    return report.model_dump_json(indent=2)


@tool
def consult_financial_agent(ticker: str, question: str) -> str:
    """Ask the FORENSIC ACCOUNTANT (Financial Analysis Agent) a focused question
    about a company's profitability, liquidity, solvency, growth, or items in
    the Notes to Financial Statements. The agent has access to XBRL-derived
    Income Statement, Balance Sheet, Cash Flow line items, and Notes for the
    given ticker. Returns a FinancialReport JSON.

    USE THIS WHEN: the user asks quantitative questions (margins, ratios,
    cash flow, debt) OR about accounting policies / red flags.

    IMPORTANT: The agent MUST ONLY use data from the database files. 
    If the data is not in the DB, it must say so. Do not hallucinate external data.

    Args:
        ticker: Stock symbol (e.g. "AAPL").
        question: The specific user question to focus on.
    """
    return _consult(FINANCIAL_AGENT_PROMPT, FinancialReport, ticker, question, "financial_inputs")


@tool
def consult_risk_agent(ticker: str, question: str) -> str:
    """Ask the BUSINESS & RISK ANALYST a focused question about business model,
    competitive moats, macro headwinds, regulatory risks, operational risks, or
    forward-looking signals from the latest 10-K's Business / MD&A / Risk
    Factors sections. Returns a BusinessReport JSON.

    USE THIS WHEN: the user asks "why" or qualitative questions about the
    business (e.g., "What were the legal risks mentioned in the 10-K?",
    "What is their competitive moat?", "What macro headwinds did they cite?").

    IMPORTANT: The agent MUST ONLY use data from the database files. 
    If the data is not in the DB, it must say so. Do not hallucinate external data.

    Args:
        ticker: Stock symbol.
        question: The specific user question to focus on.
    """
    return _consult(BUSINESS_RISK_AGENT_PROMPT, BusinessReport, ticker, question, "business_inputs")


@tool
def consult_sentiment_agent(ticker: str, question: str) -> str:
    """Ask the SENTIMENT & CONVICTION ANALYST a focused question about the
    most recent earnings-call tone, forward-guidance confidence, Q&A behavior,
    and INSIDER-TRADE CONVICTION (cross-referencing what executives said with
    what they actually did via Form 4 filings — distinguishing routine
    tax-withholding from genuine conviction trades). Returns a SentimentReport
    JSON.

    USE THIS WHEN: the user asks about management tone, behavioral signals,
    or whether insiders are "putting their money where their mouth is".

    IMPORTANT: The agent MUST ONLY use data from the database files. 
    If the data is not in the DB, it must say so. Do not hallucinate external data.

    Args:
        ticker: Stock symbol.
        question: The specific user question to focus on.
    """
    return _consult(SENTIMENT_AGENT_PROMPT, SentimentReport, ticker, question, "sentiment_inputs")


# ── Compose ───────────────────────────────────────────────────────────
def build_cio_tools():
    """Full tool set for the conversational CIO."""
    return get_sql_toolkit_tools() + [
        consult_financial_agent,
        consult_risk_agent,
        consult_sentiment_agent,
    ]
