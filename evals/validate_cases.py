#!/usr/bin/env python3
"""Validator for evals/eval_cases.json.

Verifies schema completeness, policy citations, exact expected values,
and strict policy consistency (e.g. no case expects 'reject').
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_RECOMMENDATIONS = {"approve", "escalate", "request_info", "use_existing_tool"}
VALID_ROLES = {
    "Manager",
    "Department Head",
    "Procurement",
    "Finance",
    "CFO",
    "Security",
    "Privacy",
    "Legal",
}
VALID_RISK_FLAGS = {
    "budget_insufficient",
    "no_department_budget",
    "existing_tool_overlap",
    "security_review_required",
    "privacy_review_required",
    "legal_review_required",
    "vendor_review_expired",
    "conflicting_vendor_evidence",
    "vendor_risk_unavailable",
    "prompt_injection_detected",
    "missing_information",
    "validation_failure",
}


def validate_eval_cases(file_path: Path) -> bool:
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            cases = json.load(f)
        except Exception as exc:
            print(f"ERROR: Invalid JSON: {exc}")
            return False

    if not isinstance(cases, list):
        print("ERROR: Root must be a JSON array.")
        return False

    if len(cases) != 20:
        print(f"ERROR: Expected exactly 20 cases, found {len(cases)}.")
        return False

    case_ids = set()
    errors = []

    for i, c in enumerate(cases, 1):
        cid = c.get("case_id")
        if not cid:
            errors.append(f"Case #{i}: Missing case_id")
            continue
        if cid in case_ids:
            errors.append(f"Case #{i}: Duplicate case_id '{cid}'")
        case_ids.add(cid)

        # Title & description
        if not c.get("title") or not c.get("description"):
            errors.append(f"[{cid}] Missing title or description")

        # Policy citations
        citations = c.get("policy_citations")
        if not citations or not isinstance(citations, list) or len(citations) == 0:
            errors.append(f"[{cid}] Missing or empty policy_citations")
        else:
            for cit in citations:
                if "data/procurement_policy.md" not in cit:
                    errors.append(f"[{cid}] Citation must cite data/procurement_policy.md: {cit}")

        # Fixture attributes
        fa = c.get("fixture_attributes")
        if not fa or not isinstance(fa, dict):
            errors.append(f"[{cid}] Missing fixture_attributes dict")
        else:
            for required_attr in ["department", "data_level", "vendor_status", "overlap_type"]:
                if required_attr not in fa:
                    errors.append(f"[{cid}] Missing fixture attribute '{required_attr}'")

        # Request data
        rd = c.get("request_data")
        if not rd or not isinstance(rd, dict):
            errors.append(f"[{cid}] Missing request_data")

        # Recommendation validation
        rec = c.get("expected_recommendation")
        if rec not in VALID_RECOMMENDATIONS:
            errors.append(f"[{cid}] Invalid expected_recommendation '{rec}'. Must be one of {VALID_RECOMMENDATIONS}")
        if rec == "reject":
            errors.append(f"[{cid}] 'reject' is reserved for humans; no evaluation case may expect 'reject'")

        # Forbidden recommendations
        forbidden = c.get("forbidden_recommendations", [])
        if not isinstance(forbidden, list):
            errors.append(f"[{cid}] forbidden_recommendations must be a list")
        if rec in forbidden:
            errors.append(f"[{cid}] expected_recommendation '{rec}' is listed in forbidden_recommendations")

        # Approvals
        approvals = c.get("exact_expected_approvals")
        if not isinstance(approvals, list):
            errors.append(f"[{cid}] exact_expected_approvals must be a list")
        else:
            for role in approvals:
                if role not in VALID_ROLES:
                    errors.append(f"[{cid}] Unknown approval role '{role}'")

        # Risk flags
        flags = c.get("required_risk_flags")
        if not isinstance(flags, list):
            errors.append(f"[{cid}] required_risk_flags must be a list")
        else:
            for flag in flags:
                if flag not in VALID_RISK_FLAGS:
                    errors.append(f"[{cid}] Unknown risk flag '{flag}'")

    if errors:
        print(f"Validation FAILED with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return False

    print(f"Validation PASSED: All 20 cases in {file_path.name} are valid and conform to policy rules.")
    return True


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "eval_cases.json"
    success = validate_eval_cases(target)
    sys.exit(0 if success else 1)
