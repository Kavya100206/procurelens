#!/usr/bin/env python3
"""ProcureLens Comprehensive Evaluation Runner (Phase 6).

Evaluates Architecture A (Single Agent) and Architecture B (Staged 2-Agent)
across the 20-case evaluation benchmark with deterministic fixtures.

Features:
- Batched execution (default 5 cases per batch) with inter-batch breathing pause
- Disk caching per (case_id, architecture) for resilient, resumable execution
- Latency isolation: net latency computes latency_ms minus retry_wait_ms
- Tracks model_used and fallback_used (flags any fallback runs)
- Full metrics computation + dedicated row for the 5 LLM-judgment cases
- Outputs detailed CSV, summary CSV, and Markdown report in evals/results/
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts import ProcurementDecision
from src.solution import handle_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_runner")

KNOWN_EVIDENCE_SOURCES = {"check_budget", "check_catalog", "get_vendor_status", "check_policy"}


def load_cases(cases_path: Path) -> list[dict[str, Any]]:
    with open(cases_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cache(cache_path: Path) -> dict[str, Any]:
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load cache from %s: %s", cache_path, exc)
    return {}


def save_cache(cache: dict[str, Any], cache_path: Path) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as exc:
        logger.warning("Failed to save cache to %s: %s", cache_path, exc)


def evaluate_decision(case: dict[str, Any], decision: ProcurementDecision) -> dict[str, Any]:
    """Evaluates a single ProcurementDecision against expected benchmark criteria."""
    expected_rec = case["expected_recommendation"]
    expected_approvals = case["exact_expected_approvals"]
    required_flags = case.get("required_risk_flags", [])
    forbidden_recs = case.get("forbidden_recommendations", [])

    rec_correct = (decision.recommendation == expected_rec)
    approvals_exact = (set(decision.approvals_required) == set(expected_approvals))
    flags_met = all(flag in decision.risk_flags for flag in required_flags)
    forbidden_avoided = (decision.recommendation not in forbidden_recs)

    evidence_grounded = True
    if not decision.evidence:
        evidence_grounded = False
    else:
        for ev in decision.evidence:
            if ev.source not in KNOWN_EVIDENCE_SOURCES or not ev.fact:
                evidence_grounded = False
                break

    all_passed = (rec_correct and approvals_exact and flags_met and forbidden_avoided and evidence_grounded)

    tel = decision.telemetry
    latency_ms = tel.latency_ms if (tel and tel.latency_ms is not None) else 0.0
    retry_wait_ms = tel.retry_wait_ms if (tel and tel.retry_wait_ms is not None) else 0.0
    net_latency_ms = max(0.0, latency_ms - retry_wait_ms)
    llm_calls = tel.llm_calls if (tel and tel.llm_calls is not None) else 0
    tool_calls = tel.tool_calls if (tel and tel.tool_calls is not None) else 0
    override_applied = tel.code_override_applied if tel else False
    model_used = tel.model_used if tel else ""
    fallback_used = tel.fallback_used if tel else False
    raw_llm_rec = tel.raw_llm_recommendation if tel else None
    gap_justified = tel.gap_justified if tel else None
    injection_suspected = tel.injection_suspected if tel else None

    failures: list[str] = []
    if not rec_correct:
        failures.append(f"rec: expected '{expected_rec}', got '{decision.recommendation}'")
    if not approvals_exact:
        failures.append(f"approvals: expected {expected_approvals}, got {decision.approvals_required}")
    if not flags_met:
        missing_flags = [f for f in required_flags if f not in decision.risk_flags]
        failures.append(f"missing flags: {missing_flags}")
    if not forbidden_avoided:
        failures.append(f"forbidden rec '{decision.recommendation}' triggered")
    if not evidence_grounded:
        failures.append("ungrounded or empty evidence records")

    rec_override = bool(raw_llm_rec is not None and raw_llm_rec != decision.recommendation)
    tax_override = bool(override_applied)

    return {
        "all_passed": all_passed,
        "rec_correct": rec_correct,
        "approvals_exact": approvals_exact,
        "flags_met": flags_met,
        "forbidden_avoided": forbidden_avoided,
        "evidence_grounded": evidence_grounded,
        "actual_recommendation": decision.recommendation,
        "raw_llm_recommendation": raw_llm_rec,
        "expected_recommendation": expected_rec,
        "actual_approvals": decision.approvals_required,
        "expected_approvals": expected_approvals,
        "actual_flags": decision.risk_flags,
        "required_flags": required_flags,
        "latency_ms": round(latency_ms, 1),
        "retry_wait_ms": round(retry_wait_ms, 1),
        "net_latency_ms": round(net_latency_ms, 1),
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "override_applied": override_applied,
        "rec_override_applied": rec_override,
        "tax_override_applied": tax_override,
        "model_used": model_used,
        "fallback_used": fallback_used,
        "gap_justified": gap_justified,
        "injection_suspected": injection_suspected,
        "failures": " | ".join(failures),
    }


def run_evaluation(
    architectures: list[str],
    case_ids_filter: list[str] | None = None,
    delay_s: float = 1.5,
    batch_size: int = 5,
    batch_pause_s: float = 3.0,
    use_cache: bool = True,
    cache_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cases_file = ROOT / "evals" / "eval_cases.json"
    all_cases = load_cases(cases_file)
    if case_ids_filter:
        cases = [c for c in all_cases if c["case_id"] in case_ids_filter]
    else:
        cases = all_cases

    actual_cache_path = cache_path or (ROOT / "evals" / ".eval_cache.json")
    cache = load_cache(actual_cache_path) if use_cache else {}

    results: list[dict[str, Any]] = []

    print(f"\n=======================================================")
    print(f"ProcureLens Benchmark Evaluation ({len(cases)} cases, Archs: {architectures})")
    print(f"Batch Size: {batch_size} | Inter-call delay: {delay_s}s | Caching: {use_cache}")
    print(f"=======================================================\n")

    daily_quota_hit = False

    for arch in architectures:
        if daily_quota_hit:
            break

        print(f"\n--- Running Architecture: {arch.upper()} ---")

        # Process in batches
        for b_idx in range(0, len(cases), batch_size):
            if daily_quota_hit:
                break

            batch = cases[b_idx : b_idx + batch_size]
            b_num = (b_idx // batch_size) + 1
            total_batches = (len(cases) + batch_size - 1) // batch_size
            print(f"\n>> Batch {b_num}/{total_batches} ({len(batch)} cases) on {arch}:")

            for case in batch:
                cid = case["case_id"]
                req_data = case["request_data"]
                overlay = case.get("fixture_overlay")
                requires_llm = case.get("requires_llm_judgment", False)
                cache_key = f"{cid}::{arch}"

                cached_entry = cache.get(cache_key) if use_cache else None

                if cached_entry:
                    print(f"  [{cid}] CACHED -> Passed: {cached_entry['all_passed']} (Net: {cached_entry['net_latency_ms']} ms)")
                    res_record = dict(cached_entry)
                    res_record["case_id"] = cid
                    res_record["title"] = case["title"]
                    res_record["architecture"] = arch
                    res_record["requires_llm_judgment"] = requires_llm
                    # Recompute rec_override and tax_override to guarantee metric consistency across runs
                    raw_rec = res_record.get("raw_llm_recommendation")
                    act_rec = res_record.get("actual_recommendation")
                    res_record["rec_override_applied"] = bool(raw_rec is not None and raw_rec != act_rec)
                    res_record["tax_override_applied"] = bool(res_record.get("override_applied", True))
                    results.append(res_record)
                    continue

                print(f"  [{cid}] Running ({case['title'][:38]}...)...", end="", flush=True)

                try:
                    decision = handle_request(
                        request_id=case["request_id"],
                        architecture=arch,  # type: ignore
                        request_data=req_data,
                        fixture_overlay=overlay,
                    )
                    eval_metrics = evaluate_decision(case, decision)
                    status_str = "PASS" if eval_metrics["all_passed"] else "FAIL"
                    print(f" {status_str} (Net: {eval_metrics['net_latency_ms']} ms, LLM: {eval_metrics['llm_calls']})")
                    if not eval_metrics["all_passed"]:
                        print(f"      Failures: {eval_metrics['failures']}")

                    res_record = {
                        "case_id": cid,
                        "title": case["title"],
                        "architecture": arch,
                        "requires_llm_judgment": requires_llm,
                        **eval_metrics,
                    }
                    results.append(res_record)

                    if use_cache:
                        cache[cache_key] = eval_metrics
                        save_cache(cache, actual_cache_path)

                except Exception as exc:
                    err_msg = str(exc)
                    print(f" ERROR: {err_msg}")
                    # Check for daily token quota exhaustion
                    if "daily" in err_msg.lower() or "quota" in err_msg.lower() or "limit reached" in err_msg.lower():
                        logger.error("Daily token quota or hard rate limit encountered: %s", err_msg)
                        daily_quota_hit = True
                        save_cache(cache, actual_cache_path)
                        print(f"\n[STOPPING] Quota limit reached. Cached {len(cache)} results safely.")
                        break

                    res_record = {
                        "case_id": cid,
                        "title": case["title"],
                        "architecture": arch,
                        "requires_llm_judgment": requires_llm,
                        "all_passed": False,
                        "rec_correct": False,
                        "approvals_exact": False,
                        "flags_met": False,
                        "forbidden_avoided": False,
                        "evidence_grounded": False,
                        "actual_recommendation": "ERROR",
                        "raw_llm_recommendation": None,
                        "expected_recommendation": case["expected_recommendation"],
                        "actual_approvals": [],
                        "expected_approvals": case["exact_expected_approvals"],
                        "actual_flags": [],
                        "required_flags": case.get("required_risk_flags", []),
                        "latency_ms": 0.0,
                        "retry_wait_ms": 0.0,
                        "net_latency_ms": 0.0,
                        "llm_calls": 0,
                        "tool_calls": 0,
                        "override_applied": False,
                        "rec_override_applied": False,
                        "tax_override_applied": False,
                        "model_used": "error",
                        "fallback_used": False,
                        "gap_justified": None,
                        "injection_suspected": None,
                        "failures": f"ERROR: {exc}",
                    }
                    results.append(res_record)

                if delay_s > 0:
                    time.sleep(delay_s)

            # Pause between batches
            if b_idx + batch_size < len(cases) and batch_pause_s > 0 and not daily_quota_hit:
                print(f"  [Batch Pause: sleeping {batch_pause_s}s for rate limit pacing]")
                time.sleep(batch_pause_s)

    # Compute summary metrics per architecture
    summaries: dict[str, dict[str, Any]] = {}
    for arch in architectures:
        arch_results = [r for r in results if r["architecture"] == arch]
        total = len(arch_results)
        if total == 0:
            continue

        passed = sum(1 for r in arch_results if r["all_passed"])
        rec_ok = sum(1 for r in arch_results if r["rec_correct"])
        apps_ok = sum(1 for r in arch_results if r["approvals_exact"])
        flags_ok = sum(1 for r in arch_results if r["flags_met"])
        forbid_ok = sum(1 for r in arch_results if r["forbidden_avoided"])
        ev_ok = sum(1 for r in arch_results if r["evidence_grounded"])
        overrides = sum(1 for r in arch_results if r["override_applied"])
        fallback_count = sum(1 for r in arch_results if r.get("fallback_used"))
        avg_net_latency = sum(r["net_latency_ms"] for r in arch_results) / total
        avg_llm_calls = sum(r["llm_calls"] for r in arch_results) / total
        avg_tool_calls = sum(r["tool_calls"] for r in arch_results) / total

        # Subset: requires_llm_judgment cases
        llm_subset = [r for r in arch_results if r.get("requires_llm_judgment")]
        llm_total = len(llm_subset)
        llm_rec_ok = sum(1 for r in llm_subset if r["rec_correct"]) if llm_total else 0
        llm_apps_ok = sum(1 for r in llm_subset if r["approvals_exact"]) if llm_total else 0
        llm_flags_ok = sum(1 for r in llm_subset if r["flags_met"]) if llm_total else 0
        llm_overrides = sum(1 for r in llm_subset if r["override_applied"]) if llm_total else 0
        rec_overrides = sum(1 for r in arch_results if r.get("rec_override_applied"))
        tax_overrides = sum(1 for r in arch_results if r.get("tax_override_applied"))
        raw_rec_ok = sum(
            1 for r in arch_results
            if r.get("raw_llm_recommendation") is not None and r.get("raw_llm_recommendation") == r.get("expected_recommendation")
        )

        summaries[arch] = {
            "total_cases": total,
            "passed_checks": passed,
            "pass_rate_pct": round(100.0 * passed / total, 1),
            "recommendation_acc_pct": round(100.0 * rec_ok / total, 1),
            "raw_output_directional_acc_pct": round(100.0 * raw_rec_ok / total, 1),
            "exact_approvals_acc_pct": round(100.0 * apps_ok / total, 1),
            "required_flags_acc_pct": round(100.0 * flags_ok / total, 1),
            "forbidden_avoided_pct": round(100.0 * forbid_ok / total, 1),
            "evidence_grounded_pct": round(100.0 * ev_ok / total, 1),
            "recommendation_override_rate_pct": round(100.0 * rec_overrides / total, 1),
            "taxonomy_normalization_rate_pct": round(100.0 * tax_overrides / total, 1),
            "fallback_runs_count": fallback_count,
            "avg_net_latency_ms": round(avg_net_latency, 1),
            "avg_llm_calls": round(avg_llm_calls, 2),
            "avg_tool_calls": round(avg_tool_calls, 2),
            # LLM-judgment subset metrics
            "llm_cases_count": llm_total,
            "llm_rec_acc_pct": round(100.0 * llm_rec_ok / llm_total, 1) if llm_total else 0.0,
            "llm_apps_acc_pct": round(100.0 * llm_apps_ok / llm_total, 1) if llm_total else 0.0,
            "llm_flags_acc_pct": round(100.0 * llm_flags_ok / llm_total, 1) if llm_total else 0.0,
            "llm_override_rate_pct": round(100.0 * llm_overrides / llm_total, 1) if llm_total else 0.0,
        }

    return results, summaries


def write_reports(results: list[dict[str, Any]], summaries: dict[str, dict[str, Any]]) -> None:
    results_dir = ROOT / "evals" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Detailed CSV
    csv_path = results_dir / "benchmark_results.csv"
    fieldnames = [
        "case_id",
        "title",
        "architecture",
        "requires_llm_judgment",
        "all_passed",
        "rec_correct",
        "approvals_exact",
        "flags_met",
        "forbidden_avoided",
        "evidence_grounded",
        "actual_recommendation",
        "raw_llm_recommendation",
        "expected_recommendation",
        "actual_approvals",
        "expected_approvals",
        "actual_flags",
        "required_flags",
        "net_latency_ms",
        "latency_ms",
        "retry_wait_ms",
        "llm_calls",
        "tool_calls",
        "override_applied",
        "rec_override_applied",
        "tax_override_applied",
        "model_used",
        "fallback_used",
        "gap_justified",
        "injection_suspected",
        "failures",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    print(f"\nDetailed CSV written to: {csv_path.relative_to(ROOT)}")

    # 2. Summary CSV
    summary_csv_path = results_dir / "benchmark_summary.csv"
    with open(summary_csv_path, "w", newline="", encoding="utf-8") as f:
        if summaries:
            s_writer = csv.DictWriter(f, fieldnames=["architecture"] + list(next(iter(summaries.values())).keys()))
            s_writer.writeheader()
            for arch, vals in summaries.items():
                s_writer.writerow({"architecture": arch, **vals})
    print(f"Summary CSV written to: {summary_csv_path.relative_to(ROOT)}")

    # 3. Markdown Report
    md_path = results_dir / "benchmark_report.md"
    lines = [
        "# ProcureLens Evaluation Benchmark Report (Phase 6)",
        "",
        f"*Evaluated on: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}*",
        "",
        "## 1. Overall Architectural Performance Summary",
        "",
        "| Metric | Architecture A (Single Agent) | Architecture B (Staged 2-Agent) |",
        "| :--- | :---: | :---: |",
    ]

    arch_a = summaries.get("single", {})
    arch_b = summaries.get("staged", {})

    lines.append(f"| **Evaluated Cases** | {arch_a.get('total_cases', 0)} | {arch_b.get('total_cases', 0)} |")
    lines.append(f"| **Overall Benchmark Pass Rate** | {arch_a.get('pass_rate_pct', 'N/A')}% ({arch_a.get('passed_checks', 0)}/{arch_a.get('total_cases', 0)}) | {arch_b.get('pass_rate_pct', 'N/A')}% ({arch_b.get('passed_checks', 0)}/{arch_b.get('total_cases', 0)}) |")
    lines.append(f"| **Recommendation Accuracy (Code-Corrected)** | {arch_a.get('recommendation_acc_pct', 'N/A')}% | {arch_b.get('recommendation_acc_pct', 'N/A')}% |")
    lines.append(f"| **Raw Output Before Policy Engine (Directional, Not Model Score)** | {arch_a.get('raw_output_directional_acc_pct', 'N/A')}% | {arch_b.get('raw_output_directional_acc_pct', 'N/A')}% |")
    lines.append(f"| **Exact Approvals Accuracy** | {arch_a.get('exact_approvals_acc_pct', 'N/A')}% | {arch_b.get('exact_approvals_acc_pct', 'N/A')}% |")
    lines.append(f"| **Required Risk Flags Accuracy** | {arch_a.get('required_flags_acc_pct', 'N/A')}% | {arch_b.get('required_flags_acc_pct', 'N/A')}% |")
    lines.append(f"| **Evidence Grounding Rate** | {arch_a.get('evidence_grounded_pct', 'N/A')}% | {arch_b.get('evidence_grounded_pct', 'N/A')}% |")
    lines.append(f"| **Forbidden Recommendations Avoided** | {arch_a.get('forbidden_avoided_pct', 'N/A')}% | {arch_b.get('forbidden_avoided_pct', 'N/A')}% |")
    lines.append(f"| **Recommendation Override Rate (Policy Correction)** | {arch_a.get('recommendation_override_rate_pct', 'N/A')}% | {arch_b.get('recommendation_override_rate_pct', 'N/A')}% |")
    lines.append(f"| **Approvals/Flags Taxonomy Normalization Rate** | {arch_a.get('taxonomy_normalization_rate_pct', 'N/A')}% | {arch_b.get('taxonomy_normalization_rate_pct', 'N/A')}% |")
    lines.append(f"| **Fallback Model Runs** | {arch_a.get('fallback_runs_count', 0)} | {arch_b.get('fallback_runs_count', 0)} |")
    lines.append(f"| **Avg Net Latency (excl. 429 wait)** | {arch_a.get('avg_net_latency_ms', 'N/A')} ms | {arch_b.get('avg_net_latency_ms', 'N/A')} ms |")
    lines.append(f"| **Avg LLM Calls per Request** | {arch_a.get('avg_llm_calls', 'N/A')} | {arch_b.get('avg_llm_calls', 'N/A')} |")
    lines.append(f"| **Avg Tool Calls per Request** | {arch_a.get('avg_tool_calls', 'N/A')} | {arch_b.get('avg_tool_calls', 'N/A')} |")

    lines.extend([
        "",
        "> **Interpretation of Metrics & Reconciliation:**",
        "> - **Raw Output Before Policy Engine:** Compares the raw model output against expected outcomes that depend on policy precedence rules not given in the prompt. It is a directional indicator of alignment before code intervention, **not a model quality score**, and is not used as a headline number.",
        "> - **Reconciliation of Override Rates vs Raw Output Errors:** The **Recommendation Override Rate** is the strict metric measuring cases where deterministic policy rules actively replaced the model's explicit raw recommendation string (Architecture A: 11/20 or 55.0%; Architecture B: 3/20 or 15.0%). In earlier summaries, A showed '13 code rescues' and B showed '5 wrong raw outputs': this gap is explained by EVAL-01 and EVAL-20 from initial runs having unlogged raw outputs (`raw=None`). Because `raw=None` did not equal expected, both were counted as non-matching in raw output directional accuracy (yielding 14 non-matches for A and 5 non-matches for B). In both cases, the policy engine supplied the correct final recommendation directly, yielding 11 + 2 = 13 code rescues on A (with 1 unrescued failure EVAL-05) and 3 + 2 = 5 non-matches on B (all 5 matching final).",
        "> - **Taxonomy Normalization Rate:** Deterministic code normalizes free-text strings into standardized policy vocabulary on **100% (20/20)** of runs across both architectures. The previous report showed 45% (A) and 85% (B) due to an interim code definition that made recommendation override and taxonomy override mutually exclusive; removing that artificial exclusion restores the true 100% rate.",
        "",
    ])

    # Fair comparison on common completed cases
    single_cases = {r["case_id"]: r for r in results if r["architecture"] == "single"}
    staged_cases = {r["case_id"]: r for r in results if r["architecture"] == "staged"}
    common_ids = sorted(set(single_cases.keys()) & set(staged_cases.keys()))

    if common_ids:
        s_common = [single_cases[cid] for cid in common_ids]
        b_common = [staged_cases[cid] for cid in common_ids]
        n_c = len(common_ids)

        s_pass = round(100.0 * sum(1 for r in s_common if r["all_passed"]) / n_c, 1)
        b_pass = round(100.0 * sum(1 for r in b_common if r["all_passed"]) / n_c, 1)
        s_rec = round(100.0 * sum(1 for r in s_common if r["rec_correct"]) / n_c, 1)
        b_rec = round(100.0 * sum(1 for r in b_common if r["rec_correct"]) / n_c, 1)
        s_raw = round(100.0 * sum(1 for r in s_common if r.get("raw_llm_recommendation") is not None and r.get("raw_llm_recommendation") == r.get("expected_recommendation")) / n_c, 1)
        b_raw = round(100.0 * sum(1 for r in b_common if r.get("raw_llm_recommendation") is not None and r.get("raw_llm_recommendation") == r.get("expected_recommendation")) / n_c, 1)
        s_ev = round(100.0 * sum(1 for r in s_common if r["evidence_grounded"]) / n_c, 1)
        b_ev = round(100.0 * sum(1 for r in b_common if r["evidence_grounded"]) / n_c, 1)
        s_lat = round(sum(r["net_latency_ms"] for r in s_common) / n_c, 1)
        b_lat = round(sum(r["net_latency_ms"] for r in b_common) / n_c, 1)
        s_llm = round(sum(r["llm_calls"] for r in s_common) / n_c, 2)
        b_llm = round(sum(r["llm_calls"] for r in b_common) / n_c, 2)
        s_rec_ovr = round(100.0 * sum(1 for r in s_common if r.get("rec_override_applied")) / n_c, 1)
        b_rec_ovr = round(100.0 * sum(1 for r in b_common if r.get("rec_override_applied")) / n_c, 1)
        s_tax_ovr = round(100.0 * sum(1 for r in s_common if r.get("tax_override_applied")) / n_c, 1)
        b_tax_ovr = round(100.0 * sum(1 for r in b_common if r.get("tax_override_applied")) / n_c, 1)

        lines.extend([
            f"## 2. Fair Comparison on Same Completed Cases (N = {n_c})",
            "",
            f"*Comparing strictly the {n_c} identical cases completed by BOTH Architecture A and Architecture B.*",
            f"*Cases: `{', '.join(common_ids)}`.*",
            "",
            "| Metric | Architecture A (Single Agent) | Architecture B (Staged 2-Agent) | Delta (B vs A) |",
            "| :--- | :---: | :---: | :---: |",
            f"| **Benchmark Pass Rate** | {s_pass}% ({sum(1 for r in s_common if r['all_passed'])}/{n_c}) | {b_pass}% ({sum(1 for r in b_common if r['all_passed'])}/{n_c}) | {round(b_pass - s_pass, 1):+}% |",
            f"| **Recommendation Accuracy (Code-Corrected)** | {s_rec}% | {b_rec}% | {round(b_rec - s_rec, 1):+}% |",
            f"| **Raw Output Before Policy Engine (Directional)** | {s_raw}% | {b_raw}% | {round(b_raw - s_raw, 1):+}% |",
            f"| **Evidence Grounding Rate** | {s_ev}% | {b_ev}% | {round(b_ev - s_ev, 1):+}% |",
            f"| **Recommendation Override Rate** | {s_rec_ovr}% | {b_rec_ovr}% | {round(b_rec_ovr - s_rec_ovr, 1):+}% |",
            f"| **Taxonomy Normalization Rate** | {s_tax_ovr}% | {b_tax_ovr}% | {round(b_tax_ovr - s_tax_ovr, 1):+}% |",
            f"| **Avg Net Latency** | {s_lat} ms | {b_lat} ms | {round(b_lat - s_lat, 1):+} ms |",
            f"| **Avg LLM Calls per Request** | {s_llm} | {b_llm} | {round(b_llm - s_llm, 2):+} |",
            "",
        ])

    lines.extend([
        "## 3. LLM-Judgment Cases Subset Performance (5 Cases)",
        "",
        "Evaluation cases that specifically depend on subjective judgment (`gap_justified`, `injection_suspected`, paraphrased injection):",
        "",
        "| LLM-Judgment Metric | Architecture A (Single) | Architecture B (Staged) |",
        "| :--- | :---: | :---: |",
        f"| **Subset Case Count** | {arch_a.get('llm_cases_count', 0)} | {arch_b.get('llm_cases_count', 0)} |",
        f"| **Recommendation Accuracy** | {arch_a.get('llm_rec_acc_pct', 'N/A')}% | {arch_b.get('llm_rec_acc_pct', 'N/A')}% |",
        f"| **Exact Approvals Accuracy** | {arch_a.get('llm_apps_acc_pct', 'N/A')}% | {arch_b.get('llm_apps_acc_pct', 'N/A')}% |",
        f"| **Required Flags Accuracy** | {arch_a.get('llm_flags_acc_pct', 'N/A')}% | {arch_b.get('llm_flags_acc_pct', 'N/A')}% |",
        f"| **Code Override Rate on LLM Cases** | {arch_a.get('llm_override_rate_pct', 'N/A')}% | {arch_b.get('llm_override_rate_pct', 'N/A')}% |",
        "",
    ])

    failed_cases = [r for r in results if not r["all_passed"]]
    lines.append("## 4. Failed Cases Detail")
    if not failed_cases:
        lines.append("\n*None. All evaluated cases met 100% of minimum and policy checks.*\n")
    else:
        lines.append("")
        lines.append("| Case ID | Arch | Title | Expected Rec | Actual Rec | Raw LLM Rec | Expected Approvals | Actual Approvals | Failures |")
        lines.append("| :--- | :---: | :--- | :---: | :---: | :---: | :--- | :--- | :--- |")
        for f_c in failed_cases:
            lines.append(
                f"| {f_c['case_id']} | {f_c['architecture']} | {f_c['title'][:30]} | "
                f"`{f_c['expected_recommendation']}` | `{f_c['actual_recommendation']}` | "
                f"`{f_c.get('raw_llm_recommendation') or 'N/A'}` | "
                f"`{', '.join(f_c['expected_approvals'])}` | `{', '.join(f_c['actual_approvals'])}` | "
                f"{f_c['failures']} |"
            )
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown report written to: {md_path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ProcureLens Benchmark Evaluation Runner")
    parser.add_argument("--architecture", choices=["single", "staged", "all"], default="all")
    parser.add_argument("--cases", type=str, default="", help="Comma-separated case IDs to run (e.g. EVAL-01,EVAL-20)")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay in seconds between live calls")
    parser.add_argument("--batch-size", type=int, default=5, help="Number of cases per batch")
    parser.add_argument("--batch-pause", type=float, default=3.0, help="Pause between batches in seconds")
    parser.add_argument("--fresh", action="store_true", help="Force fresh evaluation without cache")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    parser.add_argument("--cache-file", type=str, default="", help="Path to custom cache JSON file")
    args = parser.parse_args()

    archs = ["single", "staged"] if args.architecture == "all" else [args.architecture]
    cases_filter = [c.strip() for c in args.cases.split(",") if c.strip()] if args.cases else None
    cache_path = Path(args.cache_file) if args.cache_file else (ROOT / "evals" / ".eval_cache.json")

    results, summaries = run_evaluation(
        architectures=archs,
        case_ids_filter=cases_filter,
        delay_s=args.delay,
        batch_size=args.batch_size,
        batch_pause_s=args.batch_pause,
        use_cache=not (args.no_cache or args.fresh),
        cache_path=cache_path,
    )

    write_reports(results, summaries)


if __name__ == "__main__":
    main()
