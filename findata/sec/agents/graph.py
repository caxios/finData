"""
LangGraph wiring: 3 analyst agents fan out from START in parallel,
all three converge into the CIO synthesizer, then END.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import business_node, cio_node, financial_node, sentiment_node
from .state import AnalysisState


def build_graph():
    g = StateGraph(AnalysisState)

    g.add_node("financial", financial_node)
    g.add_node("business", business_node)
    g.add_node("sentiment", sentiment_node)
    g.add_node("cio", cio_node)

    # Parallel fan-out: all three analyst nodes start from START.
    g.add_edge(START, "financial")
    g.add_edge(START, "business")
    g.add_edge(START, "sentiment")

    # Fan-in: LangGraph waits for all three predecessors before running CIO.
    g.add_edge("financial", "cio")
    g.add_edge("business", "cio")
    g.add_edge("sentiment", "cio")

    g.add_edge("cio", END)

    return g.compile()
