"""
Batch test runner: processes every invoice in data/invoices/ through the
full pipeline, prints a summary table, and exports the results as both
a CSV and a styled HTML report -- so there's a shareable artifact showing
system behavior across the whole real dataset, not just console output.

Usage:
    python3 tests/run_all_invoices.py
"""

from __future__ import annotations

import csv
import glob
import os
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph import run_pipeline

INVOICE_GLOB = "data/invoices/*"
REPORTS_DIR = "reports"


def run_all() -> list[dict]:
    paths = sorted(glob.glob(INVOICE_GLOB))
    results = []
    for path in paths:
        try:
            state = run_pipeline(path)
            results.append(
                {
                    "file": os.path.basename(path),
                    "vendor": state.vendor or "—",
                    "amount": state.amount if state.amount is not None else 0.0,
                    "flags": ", ".join(f.code for f in state.validation_flags) or "none",
                    "decision": state.approval_decision.value if state.approval_decision else "—",
                    "payment": state.payment_status.value if state.payment_status else "—",
                    "reasoning": state.approval_reasoning or "",
                    "errors": "; ".join(state.errors) if state.errors else "",
                }
            )
        except Exception as e:
            results.append(
                {
                    "file": os.path.basename(path),
                    "vendor": "CRASHED",
                    "amount": 0.0,
                    "flags": "—",
                    "decision": "—",
                    "payment": "—",
                    "reasoning": "",
                    "errors": f"{type(e).__name__}: {e}",
                }
            )
            print(f"\n!!! {path} crashed:")
            traceback.print_exc()
    return results


def print_summary(results: list[dict]) -> None:
    print("\n" + "=" * 100)
    print(f"{'FILE':<28} {'VENDOR':<22} {'AMOUNT':<12} {'FLAGS':<20} {'DECISION':<10} {'PAYMENT':<10}")
    print("-" * 100)
    for r in results:
        print(
            f"{r['file']:<28} {r['vendor'][:20]:<22} ${r['amount']:<11,.2f} "
            f"{r['flags'][:18]:<20} {r['decision']:<10} {r['payment']:<10}"
        )
    print("=" * 100)


def _stats(results: list[dict]) -> dict:
    approved = [r for r in results if r["decision"] == "approved"]
    rejected = [r for r in results if r["decision"] == "rejected"]
    crashed = [r for r in results if r["vendor"] == "CRASHED"]
    return {
        "total": len(results),
        "approved": len(approved),
        "rejected": len(rejected),
        "crashed": len(crashed),
        "amount_paid": sum(r["amount"] for r in approved),
        "amount_flagged": sum(r["amount"] for r in rejected),
    }


def export_csv(results: list[dict], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)


def export_html(results: list[dict], stats: dict, path: str) -> None:
    rows = "\n".join(
        f"""<tr class="{r['decision']}">
            <td>{r['file']}</td><td>{r['vendor']}</td><td>${r['amount']:,.2f}</td>
            <td>{r['flags']}</td><td>{r['decision']}</td><td>{r['payment']}</td>
        </tr>"""
        for r in results
    )
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Invoice Processing Batch Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; background: #f7f7f8; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  .stats {{ display: flex; gap: 1.5rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .stat {{ background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .stat .num {{ font-size: 1.6rem; font-weight: 600; }}
  .stat .label {{ font-size: 0.8rem; color: #666; }}
  table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #eee; font-size: 0.9rem; }}
  th {{ background: #1a1a1a; color: white; }}
  tr.approved {{ background: #f0fdf4; }}
  tr.rejected {{ background: #fef2f2; }}
</style></head>
<body>
  <h1>Invoice Processing Batch Report</h1>
  <p style="color:#666">Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
  <div class="stats">
    <div class="stat"><div class="num">{stats['total']}</div><div class="label">Total invoices</div></div>
    <div class="stat"><div class="num">{stats['approved']}</div><div class="label">Approved & paid</div></div>
    <div class="stat"><div class="num">{stats['rejected']}</div><div class="label">Rejected</div></div>
    <div class="stat"><div class="num">${stats['amount_paid']:,.2f}</div><div class="label">Total paid</div></div>
    <div class="stat"><div class="num">${stats['amount_flagged']:,.2f}</div><div class="label">Total flagged/held</div></div>
  </div>
  <table>
    <tr><th>File</th><th>Vendor</th><th>Amount</th><th>Flags</th><th>Decision</th><th>Payment</th></tr>
    {rows}
  </table>
</body></html>"""
    with open(path, "w") as f:
        f.write(html)


def main() -> None:
    results = run_all()
    print_summary(results)
    stats = _stats(results)

    print(
        f"\nTotal: {stats['total']} | Approved: {stats['approved']} | Rejected: {stats['rejected']} "
        f"| Crashed: {stats['crashed']}"
    )
    print(f"Amount paid: ${stats['amount_paid']:,.2f} | Amount flagged/held: ${stats['amount_flagged']:,.2f}")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = os.path.join(REPORTS_DIR, f"batch_summary_{timestamp}.csv")
    html_path = os.path.join(REPORTS_DIR, f"batch_summary_{timestamp}.html")

    export_csv(results, csv_path)
    export_html(results, stats, html_path)

    print(f"\nCSV report:  {csv_path}")
    print(f"HTML report: {html_path}")


if __name__ == "__main__":
    main()