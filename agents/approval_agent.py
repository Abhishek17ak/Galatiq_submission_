"""
Approval Agent
--------------
Simulates VP-level review:
  1. Rule-based gate: invoices over $10K require extra scrutiny (a fact
     fed into the LLM's reasoning, not just a silent flag).
  2. LLM drafts an initial approve/reject decision with reasoning.
  3. Reflection/critique step: the LLM re-examines its own draft against
     the validation flags and amount, and can revise the decision if the
     draft missed or under-weighted something. This is the self-correction
     loop the case study asks for.

Includes a retry wrapper around each structured-output call: LLM tool-calling
can occasionally omit a required field (seen in practice with long critique
responses), so we catch that and retry once with the error fed back in,
rather than crashing the whole invoice.
"""

from __future__ import annotations

from typing import Literal, TypeVar

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field, ValidationError

from state import ApprovalDecision, InvoiceState

MODEL_NAME = "claude-sonnet-5"
SCRUTINY_THRESHOLD = 10_000

T = TypeVar("T", bound=BaseModel)


class ApprovalDraft(BaseModel):
    decision: Literal["approved", "rejected"]
    reasoning: str = Field(..., description="Why you reached this decision, referencing specific facts.")


class ApprovalCritique(BaseModel):
    critique: str = Field(..., description="Honest critique of the draft decision -- what it got right or missed.")
    final_decision: Literal["approved", "rejected"]
    final_reasoning: str = Field(..., description="The final reasoning after critique, may repeat or revise the draft.")


def _get_llm() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL_NAME)


def _invoke_structured(llm: ChatAnthropic, schema: type[T], prompt: str, max_retries: int = 1) -> T:
    """Self-correction wrapper: retry once if structured output fails validation
    (e.g. a required field gets dropped from a long tool-call response)."""
    structured_llm = llm.with_structured_output(schema)
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            if attempt == 0:
                return structured_llm.invoke(prompt)
            retry_prompt = (
                f"{prompt}\n\n"
                f"NOTE: your previous attempt was missing required field(s): {last_error} "
                f"Please provide ALL required fields this time."
            )
            return structured_llm.invoke(retry_prompt)
        except ValidationError as e:
            last_error = e
    raise last_error  # both attempts failed -- let the caller's error handling deal with it


def _build_context(state: InvoiceState, requires_scrutiny: bool) -> str:
    flags_summary = (
        "; ".join(f"{f.code} ({f.item}): {f.message}" for f in state.validation_flags)
        or "No validation flags -- data passed all checks."
    )
    items_summary = "; ".join(f"{i.name} x{i.quantity}" for i in state.items) or "No items extracted."

    return f"""Invoice under review:
- Vendor: {state.vendor or 'UNKNOWN'}
- Amount: ${state.amount if state.amount is not None else 'UNKNOWN'}
- Due date: {state.due_date or 'UNKNOWN'}
- Items: {items_summary}
- Validation flags: {flags_summary}
- Extraction confidence: {state.ingestion_confidence}
- Extra scrutiny required (amount > ${SCRUTINY_THRESHOLD:,}): {requires_scrutiny}
"""


DRAFT_PROMPT = """You are a VP reviewing this invoice for approval. Decide APPROVED or REJECTED.

Guidelines:
- Any validation flag indicating fraud-like signals (zero-stock item, unknown item, negative \
quantity) is serious and should usually lead to rejection unless there's a clear, reasonable \
explanation.
- A stock-exceeded flag alone may sometimes still be approvable (e.g. a legitimate large order) \
but deserves careful reasoning, especially if extra scrutiny is required.
- If extra scrutiny is required (amount over $10,000), reason more carefully and hold the \
invoice to a higher bar before approving.
- Missing critical data (vendor, amount) should generally lead to rejection.

{context}

Give your decision and reasoning."""

CRITIQUE_PROMPT = """You are critiquing a colleague's invoice approval decision before it's finalized.

{context}

Draft decision: {decision}
Draft reasoning: {reasoning}

Critique this draft honestly: did it correctly weigh the validation flags and amount? Is there \
anything it got wrong, missed, or under-weighted -- especially if extra scrutiny was required? \
If the draft is correct, say so and keep the same decision. If it's wrong, revise it.

IMPORTANT: you must provide all three fields -- critique, final_decision, and final_reasoning -- \
even if your critique is brief and the final_decision matches the draft."""


def run_approval(state: InvoiceState) -> InvoiceState:
    requires_scrutiny = state.amount is not None and state.amount > SCRUTINY_THRESHOLD
    state.requires_extra_scrutiny = requires_scrutiny

    context = _build_context(state, requires_scrutiny)
    llm = _get_llm()

    try:
        # Step 1: draft decision
        draft = _invoke_structured(llm, ApprovalDraft, DRAFT_PROMPT.format(context=context))

        # Step 2: reflection/critique pass
        critique = _invoke_structured(
            llm,
            ApprovalCritique,
            CRITIQUE_PROMPT.format(context=context, decision=draft.decision, reasoning=draft.reasoning),
        )
    except ValidationError as e:
        # Both attempts failed for some stage -- log it, default to rejection (safer than
        # silently approving something we couldn't properly reason about).
        state.errors.append(f"Approval failed after retry: {e}")
        state.approval_decision = ApprovalDecision.REJECTED
        state.approval_reasoning = "Approval agent failed to produce a valid decision after retry; defaulting to rejected for safety."
        return state

    state.approval_decision = (
        ApprovalDecision.APPROVED if critique.final_decision == "approved" else ApprovalDecision.REJECTED
    )
    state.approval_reasoning = critique.final_reasoning
    state.approval_critique = critique.critique
    return state