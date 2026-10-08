# ProcureLens Evaluation Methodology

This document details benchmark evaluation mechanics, edge-case accounting, and metric definition history across development phases for ProcureLens.

---

## Metric Definition History & Corrections

### 1. Reconciliation of Override Rates vs Raw Output Errors
The **Recommendation Override Rate** is the strict metric measuring cases where deterministic policy rules actively replaced the model's explicit raw recommendation string (Architecture A: 11/20 or 55.0%; Architecture B: 3/20 or 15.0%).

In earlier development summaries, Architecture A showed "13 code rescues" and Architecture B showed "5 wrong raw outputs". This gap is explained by `EVAL-01` and `EVAL-20` from initial runs having unlogged raw outputs (`raw=None`). Because `raw=None` did not equal expected, both were counted as non-matching in raw output directional accuracy (yielding 14 non-matches for A and 5 non-matches for B). In both cases, the policy engine supplied the correct final recommendation directly, yielding 11 + 2 = 13 code rescues on Architecture A (with 1 unrescued failure `EVAL-05`) and 3 + 2 = 5 non-matches on Architecture B (all 5 matching final).

### 2. Taxonomy Normalization Rate
Deterministic code normalizes free-text strings into standardized policy vocabulary on **100% (20/20)** of runs across both architectures.

An earlier interim report showed 45% (A) and 85% (B) due to an interim code definition that made recommendation override and taxonomy override mutually exclusive. Removing that artificial exclusion restores the true 100% rate.
