"""
Conversational ReAct CIO agent.

Built with `langgraph.prebuilt.create_react_agent` + `MemorySaver` checkpointer
so per-session memory is keyed by `thread_id` (we pass `session_id` from the
HTTP layer).

The agent has access to:
  • SQLDatabaseToolkit on insider_watchlist.db (the user's "insider_track.db").
  • consult_financial_agent / consult_risk_agent / consult_sentiment_agent.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from .llm import get_llm
from .tools import build_cio_tools


CONVERSATIONAL_CIO_PROMPT = """\
You are an interactive Chief Investment Officer of a long-only equity fund.
Use your tools to query the financial databases or ask your specialized
analysts (sub-agents) to provide data-driven answers to the user's questions.
ALWAYS base your advice on retrieved data — never invent figures or
qualitative claims.

═══════════════════════════════════════════════════════════════════════════════
TOOLS YOU HAVE
═══════════════════════════════════════════════════════════════════════════════
A. SQL toolkit on the insider-trades database (Form 4 filings):
   • sql_db_list_tables — list tables. The main one is `insider_trades`.
   • sql_db_schema      — inspect a table's schema BEFORE writing queries.
   • sql_db_query_checker — sanity-check a query before execution.
   • sql_db_query       — execute a SELECT.

   Use the SQL tools whenever the user asks for SPECIFIC numbers, transaction
   counts, dollar-volume aggregates, named insiders, code-level breakdowns, or
   historical trends in insider activity. ALWAYS list tables and inspect the
   schema before writing your first query in a session.

B. Subordinate analyst tools (each takes ticker + a focused question):
   • consult_financial_agent — quant + Notes-to-FS forensic accountant.
   • consult_risk_agent      — strategist for Business / MD&A / Risk Factors.
   • consult_sentiment_agent — earnings-call tone + insider-conviction analyst.

   Use these for QUALITATIVE questions where SQL alone won't help, e.g.:
     "What were the legal risks mentioned in AAPL's 10-K?"      → risk_agent
     "Was Tim Cook hedging on AI guidance last call?"           → sentiment_agent
     "Are NVDA's gross margins sustainable?"                    → financial_agent

═══════════════════════════════════════════════════════════════════════════════
OPERATING PROCEDURE
═══════════════════════════════════════════════════════════════════════════════
1. Decide the right tool first. Numbers, transactions, aggregates → SQL.
   Qualitative / strategic / behavioral → subordinate analyst.
2. If the user combines both (e.g., "Why did the CEO sell 30% of his stake?"),
   pull the Form 4 facts via SQL FIRST, then consult the sentiment_agent for
   interpretation, then synthesize.
3. For SQL: start with sql_db_list_tables → sql_db_schema → sql_db_query.
   Prefer SELECTs that LIMIT 50 unless the user explicitly asks for more.
4. Distinguish routine tax-withholding (transaction_code='F') from
   discretionary trades. Never call Code 'F' selling a "conviction sell".
5. Cite specific numbers and quote analysts' findings. If data is missing,
   say so explicitly and tell the user what would be needed.
6. If the user pivots to a different ticker, re-query — do not assume prior
   context still applies.
7. Be concise: 2-6 sentences for simple questions, structured bullets for
   comparisons or aggregations.

You should respond in clear, professional natural language — NOT JSON.
Use Markdown for structure when helpful (tables, bullets, bold).
"""


# Module-level singletons. MemorySaver is in-process; for multi-worker
# deployments swap to SqliteSaver / PostgresSaver from langgraph.checkpoint.
_memory = MemorySaver()
_AGENT = None


def get_cio_agent():
    """Lazy singleton — first call builds the graph, subsequent calls reuse it."""
    global _AGENT
    if _AGENT is None:
        llm = get_llm(temperature=0.2)
        tools = build_cio_tools()
        _AGENT = create_react_agent(
            llm,
            tools=tools,
            prompt=CONVERSATIONAL_CIO_PROMPT,
            checkpointer=_memory,
        )
    return _AGENT


def chat(user_message: str, session_id: str) -> str:
    """One turn of conversation. State is keyed by `session_id` (thread_id)."""
    agent = get_cio_agent()
    config = {"configurable": {"thread_id": session_id}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config=config,
    )
    final = result["messages"][-1]
    content = getattr(final, "content", str(final))
    
    # If the LLM returns a list of blocks (e.g. Anthropic/Gemini multi-modal blocks), extract text
    if isinstance(content, list):
        texts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
        return "".join(texts)
        
    return str(content)


def reset_session(session_id: str) -> None:
    """Clear the memory for a single session (best-effort with MemorySaver)."""
    try:
        _memory.delete_thread(session_id)  # langgraph >= 0.2.50
    except AttributeError:
        # Older langgraph: no public delete API; just drop the in-memory entry.
        store = getattr(_memory, "storage", None)
        if isinstance(store, dict):
            store.pop(session_id, None)
