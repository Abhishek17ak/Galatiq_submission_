"""
Ingestion Agent
---------------
Reads a raw invoice file (txt/csv/json/xml/pdf) and extracts structured
data (Vendor, Amount, Items, Due Date) using Gemini's structured output,
regardless of how messy/inconsistent the source formatting is.

Design choice: rather than writing a hand-rolled parser per file format
(which breaks the moment a vendor's CSV layout differs, as we saw with
invoice_1006 vs invoice_1007), we read the raw text/content for every
format and let the LLM do the interpretation. pdfplumber only handles
the PDF -> text step; everything past that is one unified extraction path.
"""

from __future__ import annotations

import os
from typing import Optional

import pdfplumber
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field, ValidationError

from state import InvoiceState, LineItem

load_dotenv()  # picks up ANTHROPIC_API_KEY from .env automatically

MODEL_NAME = "claude-haiku-4-5-20251001"


# --- Step 2: narrow schema for exactly what the LLM should extract ---
class ExtractedInvoice(BaseModel):
    vendor: Optional[str] = Field(None, description="Vendor/company name. Null if truly missing.")
    amount: Optional[float] = Field(None, description="Final total amount due, as a plain number.")
    due_date: Optional[str] = Field(None, description="Due date as stated or inferable, e.g. YYYY-MM-DD.")
    items: list[LineItem] = Field(default_factory=list, description="All line items with quantity.")
    notes: list[str] = Field(
        default_factory=list,
        description="Anything you had to fix, infer, or guess at (typos, missing fields, ambiguous OCR text).",
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Your confidence (0-1) that this extraction is fully correct.",
    )


EXTRACTION_PROMPT = """You are an invoice data extraction system. Extract the following fields \
from the raw invoice text below, however messy, misspelled, or inconsistently formatted it is:

- vendor (company name)
- amount (final total due — not subtotal, the actual total the vendor expects to be paid)
- due_date
- items: each with name, quantity, and unit_price if available

Handle these situations sensibly:
- Typos/abbreviations (e.g. "Vndr", "Widget A" vs "WidgetA") — normalize item names to remove \
spaces so they match a catalog naming style, but note what you normalized in `notes`.
- Multiple line items with the same product name (e.g. a bulk order with several lines of the \
same item at different prices) — keep them as SEPARATE line items, don't merge them.
- Missing or blank fields — leave them null, note it in `notes`, don't guess a fabricated value.
- Non-USD currency — note it explicitly in `notes` if you detect one (e.g. EUR), and still return \
the numeric amount as stated in the document.
- Obvious urgency/fraud language ("pay immediately", "wire transfer preferred") — note it, don't \
let it affect your extraction of the actual data.

Raw invoice content:
---
{raw_text}
---

{retry_context}
"""


def _read_raw_text(path: str) -> str:
    """Step 1: get raw text out of any supported format."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    # txt, csv, json, xml all read fine as plain text — the LLM interprets structure
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _get_llm() -> ChatAnthropic:
    return ChatAnthropic(model=MODEL_NAME, temperature=0)


def _extract(raw_text: str, retry_context: str = "") -> ExtractedInvoice:
    """Step 3: one structured-output extraction call."""
    llm = _get_llm().with_structured_output(ExtractedInvoice)
    prompt = EXTRACTION_PROMPT.format(raw_text=raw_text, retry_context=retry_context)
    return llm.invoke(prompt)


def run_ingestion(state: InvoiceState) -> InvoiceState:
    """
    Step 5: full ingestion node. Reads the file, extracts structured data,
    and writes the result into the shared InvoiceState. Includes one
    self-correction retry (Step 4) if the first pass fails or looks
    clearly broken (no vendor AND no items AND no amount = probably a
    parsing miss, worth one retry with that flagged).
    """
    raw_text = _read_raw_text(state.source_path)

    try:
        result = _extract(raw_text)
        if result.vendor is None and result.amount is None and not result.items:
            # Step 4: self-correction retry — looks like a failed extraction, try once more
            retry_context = (
                "Your previous attempt returned essentially nothing (no vendor, amount, "
                "or items). Look again more carefully — the data is present in the raw "
                "text above, just possibly oddly formatted or embedded in surrounding text."
            )
            result = _extract(raw_text, retry_context=retry_context)
    except ValidationError as e:
        # Step 4: retry once, feeding the validation error back
        try:
            result = _extract(raw_text, retry_context=f"Your previous attempt failed validation: {e}")
        except ValidationError as e2:
            state.errors.append(f"Ingestion failed after retry: {e2}")
            return state

    state.vendor = result.vendor
    state.amount = result.amount
    state.due_date = result.due_date
    state.items = result.items
    state.ingestion_notes = result.notes
    state.ingestion_confidence = result.confidence
    return state
