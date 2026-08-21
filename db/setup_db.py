"""
Sets up the local SQLite inventory database used by the Validation agent.

Seed data covers exactly the items referenced across the real invoice
dataset (data/invoices/), sized so the known test scenarios from the
README trigger correctly:

  - GadgetX stock=5   -> INV-1002 requests 20, flagged as stock exceeded
  - FakeItem stock=0  -> INV-1003 references it, flagged as zero-stock/fraud
  - SuperGizmo, MegaSprocket, WidgetC are deliberately ABSENT -> unknown item
    flags for INV-1008 (SuperGizmo, MegaSprocket) and INV-1016 (WidgetC)

unit_price is included so the validation agent can optionally cross-check
invoice pricing against catalog pricing, beyond the README's minimum ask.

Run directly: python db/setup_db.py
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")

SEED_INVENTORY = [
    # (item, stock, unit_price)
    ("WidgetA", 15, 250.00),
    ("WidgetB", 10, 500.00),
    ("GadgetX", 5, 750.00),
    ("FakeItem", 0, 1000.00),  # exists in catalog but zero stock -> fraud/flag case
    # NOTE: SuperGizmo, MegaSprocket, WidgetC are intentionally NOT seeded here.
    # They appear in invoices (1008, 1016) but not in the catalog, which is
    # exactly what should trigger the "unknown item" validation flag.
]


def get_connection() -> sqlite3.Connection:
    """Shared helper so agents connect to the same DB file consistently."""
    return sqlite3.connect(DB_PATH)


def setup_database() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS inventory")
    cursor.execute(
        """
        CREATE TABLE inventory (
            item TEXT PRIMARY KEY,
            stock INTEGER NOT NULL,
            unit_price REAL
        )
        """
    )
    cursor.executemany(
        "INSERT INTO inventory (item, stock, unit_price) VALUES (?, ?, ?)",
        SEED_INVENTORY,
    )
    conn.commit()
    conn.close()
    print(f"Inventory DB initialized at {DB_PATH} with {len(SEED_INVENTORY)} items.")


if __name__ == "__main__":
    setup_database()
