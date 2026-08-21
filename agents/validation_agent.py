"""
Validation Agent
----------------
Checks the ingested invoice data against the local SQLite inventory DB
and flags mismatches: unknown items, quantity exceeding stock, zero-stock
("fraud-flavored") items, and negative/invalid quantities.

This stage is mostly deterministic logic, not an LLM call -- the README
asks us to "verify extracted data against a mock inventory database,"
which is a lookup/comparison task, not a reasoning task. Keeping it
LLM-free here also means it's fast, free, and 100% reproducible.
"""

from __future__ import annotations

from collections import defaultdict

from db.setup_db import get_connection
from state import InvoiceState, ValidationFlag


def _get_inventory() -> dict[str, tuple[int, float | None]]:
    """Returns {item_name: (stock, unit_price)} from the DB."""
    conn = get_connection()
    rows = conn.execute("SELECT item, stock, unit_price FROM inventory").fetchall()
    conn.close()
    return {name: (stock, price) for name, stock, price in rows}


def run_validation(state: InvoiceState) -> InvoiceState:
    inventory = _get_inventory()
    flags: list[ValidationFlag] = []

    # Aggregate quantities per item name within this invoice, since bulk
    # invoices (e.g. INV-1013) list the same item across multiple lines.
    requested_qty: dict[str, int] = defaultdict(int)
    for line in state.items:
        requested_qty[line.name] += line.quantity

    for item_name, qty in requested_qty.items():
        if qty < 0:
            flags.append(
                ValidationFlag(
                    code="NEGATIVE_QTY",
                    item=item_name,
                    message=f"{item_name}: requested quantity {qty} is negative -- data integrity issue.",
                )
            )
            continue  # don't also stock-check a nonsensical quantity

        if item_name not in inventory:
            flags.append(
                ValidationFlag(
                    code="UNKNOWN_ITEM",
                    item=item_name,
                    message=f"{item_name}: not found in inventory catalog.",
                )
            )
            continue

        stock, _price = inventory[item_name]

        if stock == 0:
            flags.append(
                ValidationFlag(
                    code="ZERO_STOCK_ITEM",
                    item=item_name,
                    message=f"{item_name}: catalog shows zero stock -- treat as suspicious/fraud-flavored.",
                )
            )
        elif qty > stock:
            flags.append(
                ValidationFlag(
                    code="STOCK_EXCEEDED",
                    item=item_name,
                    message=f"{item_name}: requested {qty}, only {stock} in stock.",
                )
            )

    state.validation_flags = flags
    state.is_valid = len(flags) == 0
    return state
