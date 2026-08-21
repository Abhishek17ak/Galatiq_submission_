"""
Unit tests for the Approval agent. The LLM is mocked so these tests run
instantly and for free -- we're testing the rule-based gate, the retry
wrapper, and the fail-safe default, not the LLM's judgment quality itself
(that's proven separately via tests/run_all_invoices.py against real data).

Run: python3 -m unittest tests.test_approval
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from agents.approval_agent import ApprovalCritique, ApprovalDraft, run_approval
from state import ApprovalDecision, InvoiceState


class TestScrutinyThreshold(unittest.TestCase):
    @patch("agents.approval_agent._invoke_structured")
    def test_amount_over_10k_requires_scrutiny(self, mock_invoke):
        mock_invoke.side_effect = [
            ApprovalDraft(decision="approved", reasoning="looks fine"),
            ApprovalCritique(critique="agree", final_decision="approved", final_reasoning="looks fine"),
        ]
        state = InvoiceState(source_path="fake.txt", amount=15000.0)
        result = run_approval(state)
        self.assertTrue(result.requires_extra_scrutiny)

    @patch("agents.approval_agent._invoke_structured")
    def test_amount_under_10k_does_not_require_scrutiny(self, mock_invoke):
        mock_invoke.side_effect = [
            ApprovalDraft(decision="approved", reasoning="looks fine"),
            ApprovalCritique(critique="agree", final_decision="approved", final_reasoning="looks fine"),
        ]
        state = InvoiceState(source_path="fake.txt", amount=500.0)
        result = run_approval(state)
        self.assertFalse(result.requires_extra_scrutiny)


class TestCritiqueCanOverrideDraft(unittest.TestCase):
    @patch("agents.approval_agent._invoke_structured")
    def test_critique_can_flip_decision(self, mock_invoke):
        # Draft says approved, critique catches an issue and flips to rejected.
        mock_invoke.side_effect = [
            ApprovalDraft(decision="approved", reasoning="seemed fine at first glance"),
            ApprovalCritique(
                critique="Draft missed the zero-stock flag entirely.",
                final_decision="rejected",
                final_reasoning="Zero-stock item is a serious fraud signal, overriding the draft.",
            ),
        ]
        state = InvoiceState(source_path="fake.txt", amount=100.0)
        result = run_approval(state)
        self.assertEqual(result.approval_decision, ApprovalDecision.REJECTED)
        self.assertIn("zero-stock", result.approval_critique.lower())


class TestFailSafeDefault(unittest.TestCase):
    @patch("agents.approval_agent._invoke_structured")
    def test_defaults_to_rejected_when_llm_fails_after_retry(self, mock_invoke):
        mock_invoke.side_effect = ValidationError.from_exception_data("ApprovalDraft", [])
        state = InvoiceState(source_path="fake.txt", amount=100.0)
        result = run_approval(state)
        self.assertEqual(result.approval_decision, ApprovalDecision.REJECTED)
        self.assertTrue(len(state.errors) > 0)


if __name__ == "__main__":
    unittest.main()