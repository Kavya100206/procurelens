# ProcureLens Evaluation Benchmark Report (Phase 6)

*Evaluated on: 2026-10-07 09:43:39 UTC*

## 1. Overall Architectural Performance Summary

| Metric | Architecture A (Single Agent) | Architecture B (Staged 2-Agent) |
| :--- | :---: | :---: |
| **Evaluated Cases** | 20 | 20 |
| **Overall Benchmark Pass Rate** | 95.0% (19/20) | 100.0% (20/20) |
| **Recommendation Accuracy (Code-Corrected)** | 95.0% | 100.0% |
| **Raw Output Before Policy Engine (Directional, Not Model Score)** | 30.0% | 75.0% |
| **Exact Approvals Accuracy** | 100.0% | 100.0% |
| **Required Risk Flags Accuracy** | 100.0% | 100.0% |
| **Evidence Grounding Rate** | 100.0% | 100.0% |
| **Forbidden Recommendations Avoided** | 95.0% | 100.0% |
| **Recommendation Override Rate (Policy Correction)** | 55.0% | 15.0% |
| **Approvals/Flags Taxonomy Normalization Rate** | 100.0% | 100.0% |
| **Fallback Model Runs** | 0 | 0 |
| **Avg Net Latency (excl. 429 wait)** | 5770.0 ms | 15068.0 ms |
| **Avg LLM Calls per Request** | 3.8 | 4.85 |
| **Avg Tool Calls per Request** | 4.0 | 4.0 |

> **Interpretation of Metrics & Reconciliation:**
> - **Raw Output Before Policy Engine:** Compares the raw model output against expected outcomes that depend on policy precedence rules not given in the prompt. It is a directional indicator of alignment before code intervention, **not a model quality score**, and is not used as a headline number.
> - **Reconciliation of Override Rates vs Raw Output Errors:** The **Recommendation Override Rate** is the strict metric measuring cases where deterministic policy rules actively replaced the model's explicit raw recommendation string (Architecture A: 11/20 or 55.0%; Architecture B: 3/20 or 15.0%). In earlier summaries, A showed '13 code rescues' and B showed '5 wrong raw outputs': this gap is explained by EVAL-01 and EVAL-20 from initial runs having unlogged raw outputs (`raw=None`). Because `raw=None` did not equal expected, both were counted as non-matching in raw output directional accuracy (yielding 14 non-matches for A and 5 non-matches for B). In both cases, the policy engine supplied the correct final recommendation directly, yielding 11 + 2 = 13 code rescues on A (with 1 unrescued failure EVAL-05) and 3 + 2 = 5 non-matches on B (all 5 matching final).
> - **Taxonomy Normalization Rate:** Deterministic code normalizes free-text strings into standardized policy vocabulary on **100% (20/20)** of runs across both architectures. The previous report showed 45% (A) and 85% (B) due to an interim code definition that made recommendation override and taxonomy override mutually exclusive; removing that artificial exclusion restores the true 100% rate.

## 2. Fair Comparison on Same Completed Cases (N = 20)

*Comparing strictly the 20 identical cases completed by BOTH Architecture A and Architecture B.*
*Cases: `EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06, EVAL-07, EVAL-08, EVAL-09, EVAL-10, EVAL-11, EVAL-12, EVAL-13, EVAL-14, EVAL-15, EVAL-16, EVAL-17, EVAL-18, EVAL-19, EVAL-20`.*

| Metric | Architecture A (Single Agent) | Architecture B (Staged 2-Agent) | Delta (B vs A) |
| :--- | :---: | :---: | :---: |
| **Benchmark Pass Rate** | 95.0% (19/20) | 100.0% (20/20) | +5.0% |
| **Recommendation Accuracy (Code-Corrected)** | 95.0% | 100.0% | +5.0% |
| **Raw Output Before Policy Engine (Directional)** | 30.0% | 75.0% | +45.0% |
| **Evidence Grounding Rate** | 100.0% | 100.0% | +0.0% |
| **Recommendation Override Rate** | 55.0% | 15.0% | -40.0% |
| **Taxonomy Normalization Rate** | 100.0% | 100.0% | +0.0% |
| **Avg Net Latency** | 5770.0 ms | 15068.0 ms | +9298.0 ms |
| **Avg LLM Calls per Request** | 3.8 | 4.85 | +1.05 |

## 3. LLM-Judgment Cases Subset Performance (5 Cases)

Evaluation cases that specifically depend on subjective judgment (`gap_justified`, `injection_suspected`, paraphrased injection):

| LLM-Judgment Metric | Architecture A (Single) | Architecture B (Staged) |
| :--- | :---: | :---: |
| **Subset Case Count** | 5 | 5 |
| **Recommendation Accuracy** | 80.0% | 100.0% |
| **Exact Approvals Accuracy** | 100.0% | 100.0% |
| **Required Flags Accuracy** | 100.0% | 100.0% |
| **Code Override Rate on LLM Cases** | 100.0% | 100.0% |

## 4. Failed Cases Detail

| Case ID | Arch | Title | Expected Rec | Actual Rec | Raw LLM Rec | Expected Approvals | Actual Approvals | Failures |
| :--- | :---: | :--- | :---: | :---: | :---: | :--- | :--- | :--- |
| EVAL-05 | single | Alternative product overlap wi | `escalate` | `use_existing_tool` | `use_existing_tool` | `Department Head, Finance, Procurement, Security, Privacy, Legal` | `Department Head, Finance, Procurement, Security, Privacy, Legal` | rec: expected 'escalate', got 'use_existing_tool' | forbidden rec 'use_existing_tool' triggered |
