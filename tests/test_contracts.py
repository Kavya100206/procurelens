from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError
from src.contracts import EvidenceItem, ProcurementDecision


class ContractSchemaTests(unittest.TestCase):
    def test_valid_recommendation_literals(self):
        valid_recs = ["approve", "reject", "escalate", "request_info", "use_existing_tool"]
        for rec in valid_recs:
            decision = ProcurementDecision(
                request_id="REQ-TEST",
                recommendation=rec,
                next_step="Next step description",
            )
            self.assertEqual(decision.recommendation, rec)

    def test_invalid_recommendation_rejected(self):
        invalid_recs = ["invalid_action", "random_string", "Approve", "pending", ""]
        for bad_rec in invalid_recs:
            with self.assertRaises(ValidationError, msg=f"Expected ValidationError for {bad_rec}"):
                ProcurementDecision(
                    request_id="REQ-BAD",
                    recommendation=bad_rec,
                    next_step="Invalid recommendation test",
                )

    def test_canonical_schema_serialization_and_properties(self):
        decision = ProcurementDecision(
            request_id="REQ-1001",
            recommendation="approve",
            evidence=[
                EvidenceItem(source="budget_tool", fact="Within budget", ref="budgets.csv")
            ],
            approvals_required=["Manager", "Finance"],
            next_step="Send to manager",
        )
        data = decision.model_dump()
        self.assertIn("approvals_required", data)
        self.assertEqual(data["approvals_required"], ["Manager", "Finance"])
        self.assertEqual(data["evidence"][0]["fact"], "Within budget")
        self.assertEqual(data["evidence"][0]["ref"], "budgets.csv")

        # Backward compatibility properties
        self.assertEqual(decision.required_approvals, ["Manager", "Finance"])
        self.assertEqual(decision.evidence[0].finding, "Within budget")
        self.assertEqual(decision.evidence[0].reference, "budgets.csv")


if __name__ == "__main__":
    unittest.main()
