"""
CLI entry point for the invoice processing pipeline.

Usage:
    python main.py --invoice_path=data/invoices/invoice_1002.txt

Prints a structured summary to the console and writes a full JSON log
of the run to logs/, so every run has an auditable record beyond what
scrolls past in the terminal.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from graph import run_pipeline


def _log_path(source_path: str) -> str:
    base = os.path.splitext(os.path.basename(source_path))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.makedirs("logs", exist_ok=True)
    return os.path.join("logs", f"{base}_{timestamp}.json")


def _print_summary(state) -> None:
    print("=" * 60)
    print(f"Invoice: {state.source_path}")
    print(f"Vendor:  {state.vendor or 'UNKNOWN'}")
    print(f"Amount:  ${state.amount:,.2f}" if state.amount is not None else "Amount:  UNKNOWN")
    print(f"Extra scrutiny: {state.requires_extra_scrutiny}")

    if state.validation_flags:
        print(f"Validation flags ({len(state.validation_flags)}):")
        for f in state.validation_flags:
            print(f"  - [{f.code}] {f.message}")
    else:
        print("Validation flags: none")

    print(f"Decision: {state.approval_decision.value.upper() if state.approval_decision else 'UNKNOWN'}")
    print(f"Reasoning: {state.approval_reasoning}")
    print(f"Payment status: {state.payment_status.value if state.payment_status else 'UNKNOWN'}")

    if state.errors:
        print(f"Errors encountered: {state.errors}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the invoice processing pipeline on one invoice.")
    parser.add_argument("--invoice_path", required=True, help="Path to the invoice file to process.")
    args = parser.parse_args()

    result = run_pipeline(args.invoice_path)

    _print_summary(result)

    log_path = _log_path(args.invoice_path)
    with open(log_path, "w") as f:
        f.write(result.model_dump_json(indent=2))
    print(f"Full run log written to {log_path}")


if __name__ == "__main__":
    main()