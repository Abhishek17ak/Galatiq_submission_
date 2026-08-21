"""
Payment Agent
-------------
Final stage: if approved, call the mock payment function. If rejected,
log the rejection with the reasoning already produced by the Approval
agent. No LLM call needed here -- this is a deterministic action step.
"""

from __future__ import annotations

from state import ApprovalDecision, InvoiceState, PaymentStatus


def mock_payment(vendor: str, amount: float) -> dict:
    """Mock payment function, as specified in the README."""
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}


def run_payment(state: InvoiceState) -> InvoiceState:
    if state.approval_decision == ApprovalDecision.APPROVED:
        result = mock_payment(state.vendor or "UNKNOWN VENDOR", state.amount or 0.0)
        state.payment_status = PaymentStatus.PAID if result.get("status") == "success" else PaymentStatus.NOT_PAID
    else:
        state.payment_status = PaymentStatus.NOT_PAID
        state.rejection_log = (
            f"Invoice from '{state.vendor}' for ${state.amount} was rejected.\n"
            f"Reasoning: {state.approval_reasoning}"
        )
    return state
