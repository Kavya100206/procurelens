# Planted Bugs & Audit Findings (BUGS.md)

This document tracks all bugs, inconsistencies, and edge-case vulnerabilities identified during the audit of the starter pack for **ProcureLens**, along with their implementation status across phases.

---

### Bug 1: Test Discovery Import Failure (`tests/test_mock_api.py`)
- **Status:** Fixed in Phase 0
- **Symptom:** Running `python -m unittest discover -s tests` failed with `ModuleNotFoundError: No module named 'mock_api'`.
- **Root Cause:** `test_mock_api.py` attempted to import `from mock_api.app import app` without ensuring the project root was included in `sys.path`.
- **Fix:** Added dynamic root path insertion to `sys.path` at the top of `tests/test_mock_api.py`.

---

### Bug 2: Unhandled Outages & Lack of Retry / Graceful Fallback (`src/vendor_client.py`)
- **Status:** Fixed in Phase 0
- **Symptom:** When querying the mock vendor-risk API for an unavailable service (such as `NimbusAI`, which returns HTTP 503), an unregistered vendor (HTTP 404), or during connection timeouts, the client invoked `response.raise_for_status()`, causing unhandled exceptions (`requests.HTTPError`, `requests.ConnectionError`) that crashed the calling process.
- **Root Cause:** `src/vendor_client.py:get_vendor_risk()` had no timeout handling, retry logic with backoff, or structured error fallback.
- **Fix:** Enhanced `get_vendor_risk()` with configurable retries, exponential backoff, and graceful return dictionaries (`{"error": "unavailable", ...}`, `{"error": "not_found", ...}`) so downstream tools and agents flag `vendor_risk_unavailable` instead of crashing.

---

### Bug 3: Inconsistent Financial Column Naming (`purchase_history.csv` vs `software_catalog.csv`)
- **Status:** Fixed in Phase 0
- **Symptom:** `purchase_history.csv` names its annual cost column `annual_amount_usd`, whereas `software_catalog.csv` and `requests.json` use `annual_cost_usd`. Any query expecting `annual_cost_usd` on purchase history failed with `KeyError: 'annual_cost_usd'`.
- **Root Cause:** Inconsistent column naming across synthetic CSV datasets.
- **Fix:** Updated `src/data_access.py:load_purchase_history()` to normalize the DataFrame so both `annual_amount_usd` and `annual_cost_usd` are accessible.

---

### Bug 4: Schema Contract Compatibility (`src/contracts.py`)
- **Status:** Fixed in Phase 0
- **Symptom:** Requirements specify output fields `approvals_required` and `evidence` with `fact` and `ref`, whereas starter `src/contracts.py` defined `required_approvals` and `finding` / `reference`.
- **Root Cause:** Naming divergence between problem specification and starter Pydantic models.
- **Fix:** Added Pydantic `AliasChoices` and bidirectional property getters in `src/contracts.py` for full compatibility.

---

### Bug 5: Department Budget Gap for "Go To Market" (`employees.csv` vs `department_budgets.csv`)
- **Status:** Documented, fix in Phase 2 (Policy behavior pending user confirmation in Phase 2)
- **Symptom:** In `employees.csv`, Director `Robert King` (`E007`) is assigned to department `Go To Market`. However, `department_budgets.csv` only defines budgets for `Marketing`, `Engineering`, `Sales`, `Finance`, `Customer Success`, and `Operations`. Any budget check for E007 fails with missing department data.
- **Root Cause:** Discrepancy between organizational hierarchy and budget tables. Robert King manages Sales (`E003`) and Customer Success (`E005`), but `Go To Market` has no budget allocation in the snapshot.
- **Fix Planned:** Clarify expected policy behavior with user in Phase 2 open questions and implement explicit deterministic handling in `tools/check_budget`.

---

### Bug 6: Fragile Date Parsing on Empty or Null Vendor Review Dates
- **Status:** Documented, fix in Phase 2
- **Symptom:** In `vendors.csv`, `security_review_date` is empty string `""` for `BrandBoard`, `GrowthForge`, and `NimbusAI`. In `vendor_risk.json`, `last_review_date` is `null` or missing. Standard `date.fromisoformat()` crashes with `ValueError: Invalid isoformat string: ''` or `TypeError: fromisoformat: argument must be str`.
- **Root Cause:** Datasets represent pending or uncompleted security reviews with empty strings and `None`.
- **Fix Planned:** Implement safe ISO date parser utility in `tools/get_vendor_status` and `tools/check_policy` that safely interprets falsy/empty values as unreviewed/pending.

---

### Bug 7: Stale Review Date and Conflicting Evidence for `SignalWatch`
- **Status:** Documented, fix in Phase 2
- **Symptom:** In `vendors.csv`, `SignalWatch` has `security_status: Approved` with `security_review_date: 2025-07-01`. As of snapshot reference date (`2026-09-30`), this review is 456 days old (exceeding the 365-day validity threshold). Concurrently, `vendor_risk.json` marks it as `security_review_status: expired`. Any naive tool trusting `vendors.csv` without computing age falsely treats the vendor as approved.
- **Root Cause:** The internal registry record is stale (`"Registry has not yet been refreshed with latest review state"`), deliberately conflicting with the live external service.
- **Fix Planned:** Enforce 365-day validity comparison against reference date `2026-09-30` in `tools/check_policy` and `tools/get_vendor_status` to flag `vendor_review_expired` and `conflicting_vendor_evidence`.

---

### Bug 8: Threshold Boundary Logic (`>` vs `>=`) in Approval & Legal Rules
- **Status:** Documented, fix in Phase 2
- **Symptom:** Policy Section 4 specifies tiered business approval thresholds (`Up to $1,000`, `$1,000.01 - $10,000`, `$10,000.01 - $25,000`, `Above $25,000`). Policy Section 7 specifies that Legal review is required when a vendor is new and annual spend is `$10,000 or more`. If threshold logic uses `amount > 10000`, a request of exactly `$10,000` with a new vendor fails to trigger required Legal review.
- **Root Cause:** Standard boundary ambiguity when implementing strict vs inclusive inequalities.
- **Fix Planned:** Strictly code deterministic boundary logic in `tools/check_policy` (`<= 1000`, `<= 10000`, `<= 25000`, and `annual_cost_usd >= 10000` for new vendor legal review).
