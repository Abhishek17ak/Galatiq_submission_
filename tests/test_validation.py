"""
Unit tests for the Validation agent. Fully deterministic -- no LLM calls,
no mocking needed. Assumes db/inventory.db has been set up with the
standard seed data (WidgetA=15, WidgetB=10, GadgetX=5, FakeItem=0).

Run: python3 -m unittest tests.test_validation
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.validation_agent import run_validation
from state import InvoiceState, LineItem


class TestValidationAgent(unittest.TestCase):
    def test_clean_invoice_passes(self):
        state = InvoiceState(source_path="fake.txt", items=[LineItem(name="WidgetA", quantity=6)])
        result = run_validation(state)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.validation_flags, [])

    def test_stock_exceeded(self):
        state = InvoiceState(source_path="fake.txt", items=[LineItem(name="GadgetX", quantity=20)])
        result = run_validation(state)
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.validation_flags), 1)
        self.assertEqual(result.validation_flags[0].code, "STOCK_EXCEEDED")

    def test_zero_stock_item_flagged_distinctly(self):
        state = InvoiceState(source_path="fake.txt", items=[LineItem(name="FakeItem", quantity=100)])
        result = run_validation(state)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation_flags[0].code, "ZERO_STOCK_ITEM")

    def test_unknown_item(self):
        state = InvoiceState(source_path="fake.txt", items=[LineItem(name="SuperGizmo", quantity=5)])
        result = run_validation(state)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation_flags[0].code, "UNKNOWN_ITEM")

    def test_negative_quantity(self):
        state = InvoiceState(source_path="fake.txt", items=[LineItem(name="WidgetA", quantity=-5)])
        result = run_validation(state)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation_flags[0].code, "NEGATIVE_QTY")

    def test_quantities_aggregated_across_multiple_lines(self):
        # Mirrors INV-1013: same item split across several line items in one invoice.
        state = InvoiceState(
            source_path="fake.txt",
            items=[
                LineItem(name="WidgetA", quantity=10),
                LineItem(name="WidgetA", quantity=10),
            ],
        )
        result = run_validation(state)
        # 10 + 10 = 20, exceeds stock of 15, even though no single line does
        self.assertEqual(result.validation_flags[0].code, "STOCK_EXCEEDED")


if __name__ == "__main__":
    unittest.main()