"""
LangGraph orchestration for the invoice processing pipeline.

Wires Ingestion -> Validation -> Approval -> Payment into a single
StateGraph. The graph is linear (no conditional branching needed between
stages -- Approval and Payment already make their own internal decisions
based on the state they receive), but using LangGraph here still gives us:
  - A single, inspectable pipeline definition
  - Consistent state passing via our shared InvoiceState schema
  - A natural place to hook in per-node logging
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from agents.approval_agent import run_approval
from agents.ingestion_agent import run_ingestion
from agents.payment_agent import run_payment
from agents.validation_agent import run_validation
from state import InvoiceState


def _ingestion_node(state: InvoiceState) -> InvoiceState:
    return run_ingestion(state)


def _validation_node(state: InvoiceState) -> InvoiceState:
    return run_validation(state)


def _approval_node(state: InvoiceState) -> InvoiceState:
    return run_approval(state)


def _payment_node(state: InvoiceState) -> InvoiceState:
    return run_payment(state)


def build_graph():
    graph = StateGraph(InvoiceState)

    graph.add_node("ingestion", _ingestion_node)
    graph.add_node("validation", _validation_node)
    graph.add_node("approval", _approval_node)
    graph.add_node("payment", _payment_node)

    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "validation")
    graph.add_edge("validation", "approval")
    graph.add_edge("approval", "payment")
    graph.add_edge("payment", END)

    return graph.compile()


def run_pipeline(source_path: str) -> InvoiceState:
    """Runs one invoice through the full compiled graph."""
    compiled = build_graph()
    initial_state = InvoiceState(source_path=source_path)
    result_dict = compiled.invoke(initial_state)
    return InvoiceState(**result_dict)