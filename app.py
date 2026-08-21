"""
Streamlit UI for the invoice processing pipeline.

Lets a user pick a real invoice from data/invoices/ (or upload one),
process it through the exact same LangGraph pipeline used by the CLI,
and see the result rendered clearly -- decision, reasoning, flags,
and extracted data.

Run: streamlit run app.py
"""

from __future__ import annotations

import glob
import os

import streamlit as st

from graph import run_pipeline
from state import ApprovalDecision

st.set_page_config(page_title="Invoice Processor", page_icon="📄", layout="centered")

st.title("📄 Invoice Processing Automation")
st.caption("Multi-agent pipeline: Ingestion → Validation → Approval → Payment")

# --- Invoice selection ---
sample_paths = sorted(glob.glob("data/invoices/*"))
sample_names = [os.path.basename(p) for p in sample_paths]

col1, col2 = st.columns([2, 1])
with col1:
    selected_name = st.selectbox("Choose a sample invoice", sample_names)
selected_path = os.path.join("data/invoices", selected_name) if selected_name else None

process_clicked = st.button("▶ Process Invoice", type="primary", use_container_width=True)

if process_clicked and selected_path:
    with st.spinner("Running pipeline (Ingestion → Validation → Approval → Payment)..."):
        result = run_pipeline(selected_path)

    # --- Decision badge ---
    is_approved = result.approval_decision == ApprovalDecision.APPROVED
    if is_approved:
        st.success(f"✅ APPROVED — Paid ${result.amount:,.2f} to {result.vendor}")
    else:
        st.error(f"❌ REJECTED — ${result.amount:,.2f} held for review")

    # --- Key fields ---
    st.subheader("Extracted Data")
    c1, c2, c3 = st.columns(3)
    c1.metric("Vendor", result.vendor or "Unknown")
    c2.metric("Amount", f"${result.amount:,.2f}" if result.amount is not None else "Unknown")
    c3.metric("Extra Scrutiny", "Yes" if result.requires_extra_scrutiny else "No")

    if result.items:
        st.table(
            [{"Item": i.name, "Quantity": i.quantity, "Unit Price": i.unit_price} for i in result.items]
        )

    # --- Validation flags ---
    st.subheader("Validation Flags")
    if result.validation_flags:
        for f in result.validation_flags:
            st.warning(f"**{f.code}** — {f.message}")
    else:
        st.info("No validation flags — data passed all checks.")

    # --- Approval reasoning ---
    st.subheader("Approval Reasoning")
    with st.expander("Draft → Critique → Final decision", expanded=True):
        st.markdown(f"**Final reasoning:** {result.approval_reasoning}")
        if result.approval_critique:
            st.markdown(f"**Self-critique:** {result.approval_critique}")

    # --- Ingestion notes ---
    if result.ingestion_notes:
        with st.expander("Ingestion notes (typos fixed, ambiguities resolved, etc.)"):
            for note in result.ingestion_notes:
                st.markdown(f"- {note}")

    if result.errors:
        st.error(f"Errors encountered: {result.errors}")

elif process_clicked and not selected_path:
    st.warning("Please select an invoice first.")
else:
    st.info("Select an invoice above and click **Process Invoice** to run it through the pipeline.")