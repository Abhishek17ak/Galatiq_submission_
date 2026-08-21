"""
Shared state schema for the invoice processing pipeline.

This is the single object that flows through Ingestion -> Validation ->
Approval -> Payment in the LangGraph graph. Each agent reads what it
needs and writes its own fields; nothing is deleted along the way, so
the final state is a full audit trail of the whole run.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    name: str
    quantity: int
    unit_price: Optional[float] = None


class ValidationFlag(BaseModel):
    code: str  # e.g. "UNKNOWN_ITEM", "STOCK_EXCEEDED", "NEGATIVE_QTY", "ZERO_STOCK_ITEM"
    item: Optional[str] = None
    message: str


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentStatus(str, Enum):
    PAID = "paid"
    NOT_PAID = "not_paid"


class InvoiceState(BaseModel):
    # --- input ---
    source_path: str

    # --- set by Ingestion agent ---
    vendor: Optional[str] = None
    amount: Optional[float] = None
    items: list[LineItem] = Field(default_factory=list)
    due_date: Optional[str] = None
    ingestion_notes: list[str] = Field(default_factory=list)  # typos fixed, fields inferred, etc.
    ingestion_confidence: Optional[float] = None

    # --- set by Validation agent ---
    validation_flags: list[ValidationFlag] = Field(default_factory=list)
    is_valid: Optional[bool] = None

    # --- set by Approval agent ---
    approval_decision: Optional[ApprovalDecision] = None
    approval_reasoning: Optional[str] = None
    approval_critique: Optional[str] = None  # the reflection/self-critique step
    requires_extra_scrutiny: bool = False  # True when amount > $10K

    # --- set by Payment agent ---
    payment_status: Optional[PaymentStatus] = None
    rejection_log: Optional[str] = None

    # --- run metadata ---
    errors: list[str] = Field(default_factory=list)  # any hard failures along the way
