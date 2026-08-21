"""
Unit tests for the Ingestion agent. The LLM call is mocked so these tests
run instantly, for free, without needing an API key -- we're testing our
own logic (file reading across formats, retry behavior, state merging),
not Gemini/Claude's extraction quality itself (that's proven separately
via tests/run_all_invoices.py against real data).

Run: python3 -m unittest tests.test_ingestion
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.ingestion_agent import ExtractedInvoice, _read_raw_text, run_ingestion
from state import InvoiceState, LineItem


class TestReadRawText(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_fixtures")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_reads_txt(self):
        path = self._write("sample.txt", "Vendor: Test Co\nAmount: 100")
        self.assertIn("Test Co", _read_raw_text(path))

    def test_reads_csv(self):
        path = self._write("sample.csv", "field,value\nvendor,Test Co")
        self.assertIn("vendor", _read_raw_text(path))

    def test_reads_json(self):
        path = self._write("sample.json", '{"vendor": "Test Co"}')
        self.assertIn("Test Co", _read_raw_text(path))

    def test_reads_xml(self):
        path = self._write("sample.xml", "<invoice><vendor>Test Co</vendor></invoice>")
        self.assertIn("Test Co", _read_raw_text(path))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


class TestRunIngestion(unittest.TestCase):
    @patch("agents.ingestion_agent._extract")
    def test_successful_extraction_populates_state(self, mock_extract):
        mock_extract.return_value = ExtractedInvoice(
            vendor="Test Vendor",
            amount=500.0,
            due_date="2026-01-01",
            items=[LineItem(name="WidgetA", quantity=2)],
            notes=["nothing unusual"],
            confidence=0.9,
        )
        state = InvoiceState(source_path=os.path.join(os.path.dirname(__file__), "test_ingestion.py"))
        result = run_ingestion(state)

        self.assertEqual(result.vendor, "Test Vendor")
        self.assertEqual(result.amount, 500.0)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.errors, [])

    @patch("agents.ingestion_agent._extract")
    def test_retries_once_on_empty_extraction(self, mock_extract):
        # First call returns nothing useful, second call (the retry) succeeds.
        mock_extract.side_effect = [
            ExtractedInvoice(vendor=None, amount=None, due_date=None, items=[], notes=[], confidence=0.1),
            ExtractedInvoice(
                vendor="Recovered Vendor", amount=100.0, due_date=None,
                items=[], notes=["recovered on retry"], confidence=0.8,
            ),
        ]
        state = InvoiceState(source_path=os.path.join(os.path.dirname(__file__), "test_ingestion.py"))
        result = run_ingestion(state)

        self.assertEqual(mock_extract.call_count, 2)
        self.assertEqual(result.vendor, "Recovered Vendor")


if __name__ == "__main__":
    unittest.main()