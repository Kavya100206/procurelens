from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_access import load_employees
from tools.check_budget import check_budget
from tools.check_catalog import check_catalog
from tools.get_vendor_status import get_vendor_status
from tools.check_policy import check_policy, scan_prompt_injection


class OfflineEvalCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases_path = ROOT / "evals" / "eval_cases.json"
        with open(cases_path, "r", encoding="utf-8") as f:
            cls.cases = json.load(f)
        cls.employees_df = load_employees()

    def test_twenty_cases_present(self):
        self.assertEqual(len(self.cases), 20)

    def test_all_cases_offline_deterministic_execution(self):
        """Runs all 20 evaluation cases through deterministic policy logic without external LLM calls."""
        for case in self.cases:
            cid = case["case_id"]
            req = case["request_data"]
            overlay = case.get("fixture_overlay")

            # Determine department
            emp_match = self.employees_df[self.employees_df["employee_id"] == req.get("requester_id")]
            department = emp_match.iloc[0]["department"] if not emp_match.empty else None

            # 1. Budget tool
            amt = req.get("annual_cost_usd")
            budget_res = check_budget(department=department or "", amount=amt, fixture_overlay=overlay)

            # 2. Catalog tool
            cat = req.get("category")
            ven = req.get("vendor_name")
            prod = req.get("product_name")
            catalog_res = check_catalog(
                category=cat,
                vendor_name=ven,
                product_name=prod,
                fixture_overlay=overlay,
            )

            # 3. Vendor status tool
            vendor_res = None
            if ven:
                vendor_res = get_vendor_status(vendor_name=ven, fixture_overlay=overlay)

            # 4. Prompt injection scan
            justification = req.get("business_justification", "")
            vendor_notes = vendor_res.get("notes") if vendor_res else ""
            catalog_notes = catalog_res.get("matches", [{}])[0].get("notes", "") if catalog_res.get("matches") else ""
            injection_detected = scan_prompt_injection(justification, vendor_notes, catalog_notes)

            # 5. Gap justified logic
            gap_justified = overlay.get("gap_justified", True) if overlay else True

            # 6. Check policy
            policy_res = check_policy(
                amount=amt,
                data_access_level=req.get("data_access_level"),
                vendor_status=vendor_res,
                department=department,
                budget_result=budget_res,
                requested_integrations=req.get("requested_integrations", []),
                user_count=req.get("user_count"),
                has_catalog_overlap=bool(catalog_res.get("has_overlap")),
                overlap_type=catalog_res.get("overlap_type", "none"),
                gap_justified=gap_justified,
                matched_catalog_product=catalog_res.get("matched_product"),
                prompt_injection_detected=injection_detected,
                business_justification=justification,
                vendor_notes=vendor_notes,
            )

            # Assertions
            expected_rec = case["expected_recommendation"]
            expected_apps = case["exact_expected_approvals"]
            required_flags = case["required_risk_flags"]
            forbidden_recs = case.get("forbidden_recommendations", [])

            with self.subTest(case_id=cid, title=case["title"]):
                # Recommendation
                self.assertEqual(
                    policy_res["recommendation"],
                    expected_rec,
                    f"[{cid}] Expected recommendation '{expected_rec}', got '{policy_res['recommendation']}'",
                )

                # Forbidden recommendations
                self.assertNotIn(
                    policy_res["recommendation"],
                    forbidden_recs,
                    f"[{cid}] Recommendation '{policy_res['recommendation']}' is forbidden: {forbidden_recs}",
                )

                # Exact approvals
                self.assertEqual(
                    policy_res["approvals_required"],
                    expected_apps,
                    f"[{cid}] Expected approvals {expected_apps}, got {policy_res['approvals_required']}",
                )

                # Required risk flags
                for flag in required_flags:
                    self.assertIn(
                        flag,
                        policy_res["risk_flags"],
                        f"[{cid}] Required flag '{flag}' not in risk_flags {policy_res['risk_flags']}",
                    )


if __name__ == "__main__":
    unittest.main()
