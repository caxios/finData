"""
Pydantic v2 schemas for each agent's structured output.
Used with `llm.with_structured_output(Schema)` so Gemini returns valid JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── Financial Analysis Agent ──────────────────────────────────────────
class RedFlag(BaseModel):
    severity: Literal["low", "medium", "high"]
    description: str = Field(..., description="What the red flag is, in plain English.")
    evidence: str = Field(
        ...,
        description="Cite the specific line item, ratio, or note key that triggers this flag.",
    )


class FinancialReport(BaseModel):
    profitability: str = Field(
        ...,
        description="Assessment of margins (gross/operating/net), trend over the periods provided.",
    )
    liquidity: str = Field(
        ...,
        description="Current ratio, quick ratio, working capital, ability to meet near-term obligations.",
    )
    solvency: str = Field(
        ...,
        description="Leverage, debt-to-equity, interest coverage, long-term debt sustainability.",
    )
    growth_trajectory: str = Field(
        ...,
        description="Revenue, earnings, and cash-flow growth trajectory across the periods provided.",
    )
    notes_findings: list[str] = Field(
        default_factory=list,
        description="Material findings derived from the Notes to Financial Statements (each item must reference a note key).",
    )
    accounting_red_flags: list[RedFlag] = Field(
        default_factory=list,
        description="Forensic concerns: aggressive revenue recognition, off-balance-sheet items, related-party transactions, accounting policy changes, etc.",
    )
    overall_assessment: str = Field(
        ...,
        description="Two-to-three sentence bottom-line on the company's quantitative health.",
    )


# ── Business & Risk Analysis Agent ────────────────────────────────────
class BusinessReport(BaseModel):
    business_model: str = Field(
        ...,
        description="How the company makes money: products, segments, customers, geographic mix.",
    )
    competitive_moat: str = Field(
        ...,
        description="Sources of durable competitive advantage (network effects, scale, brand, IP, switching costs).",
    )
    macro_headwinds: list[str] = Field(
        default_factory=list,
        description="Macro / industry headwinds disclosed or implied (each item one sentence).",
    )
    regulatory_risks: list[str] = Field(
        default_factory=list,
        description="Regulatory, legal, or compliance risks disclosed in Risk Factors.",
    )
    operational_risks: list[str] = Field(
        default_factory=list,
        description="Supply chain, key-personnel, cybersecurity, customer-concentration, and similar operational risks.",
    )
    mda_signals: list[str] = Field(
        default_factory=list,
        description="Forward-looking signals from MD&A: management's stated priorities, capital-allocation plans, segment outlook.",
    )
    overall_assessment: str = Field(
        ...,
        description="Two-to-three sentence bottom-line on business strength vs. risk exposure.",
    )


# ── Sentiment & Conviction Analysis Agent ─────────────────────────────
class NotableQuote(BaseModel):
    speaker: str = Field(..., description="Name or role of the speaker (e.g., 'CEO Tim Cook').")
    quote: str = Field(..., description="Direct quote from the transcript.")
    interpretation: str = Field(..., description="Why this quote matters — confident, defensive, evasive, etc.")


class NotableInsiderTrade(BaseModel):
    owner_name: str = Field(..., description="Name of the insider (e.g., 'Tim Cook').")
    officer_title: str | None = Field(
        None,
        description="Officer title or role (e.g., 'CEO', 'CFO', 'Director'). Empty if not an officer.",
    )
    transaction_date: str = Field(..., description="ISO transaction date.")
    transaction_code: str = Field(
        ...,
        description="SEC Form 4 transaction code (P=purchase, S=sale, F=tax-withholding, M=option exercise, A=award, D=disposition to issuer, etc.).",
    )
    acquired_or_disposed: Literal["A", "D", ""] = Field(
        ...,
        description="A=acquired, D=disposed.",
    )
    amount: float = Field(..., description="Number of shares in the transaction.")
    trade_ratio_pct: float | None = Field(
        None,
        description="Percentage of the insider's holdings transacted (key conviction signal).",
    )
    transaction_value: float | None = Field(None, description="USD dollar value of the transaction.")
    is_routine_tax_withholding: bool = Field(
        ...,
        description="True if the trade is routine tax-withholding (typically transaction_code='F') and should NOT be read as conviction signal.",
    )
    interpretation: str = Field(
        ...,
        description="What this trade signals — conviction buy, conviction sell, routine withholding, option exercise, etc.",
    )


class SentimentReport(BaseModel):
    # ── Transcript-based signals ──
    overall_tone: Literal["bullish", "cautiously_optimistic", "neutral", "cautious", "bearish"]
    forward_guidance_confidence: str = Field(
        ...,
        description="How confident management sounds about forward guidance: hedging language, retraction risk, conviction level.",
    )
    qa_evasiveness: str = Field(
        ...,
        description="Behavior during Q&A: did they answer directly, deflect, pivot, or refuse? Cite specifics.",
    )
    notable_quotes: list[NotableQuote] = Field(default_factory=list)
    sentiment_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Transcript-only sentiment in [-1, 1] where -1 is strongly bearish, +1 is strongly bullish.",
    )

    # ── Insider-trading signals (Form 4) ──
    insider_activity_summary: str = Field(
        ...,
        description="Plain-English summary of insider trading activity over the period: net buying vs selling, who participated, dollar magnitude. Explicitly call out routine tax-withholding trades you EXCLUDED from conviction analysis.",
    )
    notable_insider_trades: list[NotableInsiderTrade] = Field(
        default_factory=list,
        description="3-10 most material insider trades, with conviction interpretation.",
    )

    # ── Cross-reference: tone vs. insider conviction ──
    conviction_signal: Literal[
        "strong_positive_alignment",
        "positive_alignment",
        "neutral",
        "minor_contradiction",
        "major_contradiction",
        "no_data",
    ] = Field(
        ...,
        description=(
            "Cross-reference between transcript tone and insider trading actions. "
            "strong_positive_alignment = bullish tone + meaningful insider buying; "
            "major_contradiction = bullish tone + meaningful insider selling (excluding routine tax-withholding); "
            "no_data = insider trading data missing."
        ),
    )
    conviction_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description=(
            "Combined conviction score in [-1, 1]. Positive when insiders 'put their money where their mouth is'; "
            "negative when insiders sell while management talks bullishly. Routine tax-withholding does NOT count."
        ),
    )

    overall_assessment: str = Field(
        ...,
        description="Two-to-three sentence bottom-line synthesizing transcript tone AND insider-trade conviction.",
    )


# ── CIO Agent (final memo) ────────────────────────────────────────────
class Evidence(BaseModel):
    financial: list[str] = Field(
        default_factory=list,
        description="Concrete financial evidence supporting the recommendation (numbers, ratios, note keys).",
    )
    business: list[str] = Field(
        default_factory=list,
        description="Concrete business / risk evidence (moats, headwinds, regulatory).",
    )
    sentiment: list[str] = Field(
        default_factory=list,
        description="Concrete sentiment evidence (direct quotes, tone observations).",
    )


class InvestmentMemo(BaseModel):
    ticker: str
    as_of: str = Field(..., description="ISO date string for the date this memo was generated.")
    recommendation: Literal["BUY", "HOLD", "SELL"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    thesis: str = Field(..., description="One-paragraph investment thesis.")
    key_drivers: list[str] = Field(
        default_factory=list,
        description="Top reasons supporting the recommendation.",
    )
    key_risks: list[str] = Field(
        default_factory=list,
        description="Top risks that could invalidate the recommendation.",
    )
    evidence: Evidence
    memo_markdown: str = Field(
        ...,
        description="Human-readable Markdown memo combining all sections above into a polished investment memo.",
    )
