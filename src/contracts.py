from __future__ import annotations

from typing import Literal
from pydantic import AliasChoices, BaseModel, Field

Recommendation = Literal[
    "approve",
    "reject",
    "escalate",
    "request_info",
    "use_existing_tool",
]


class EvidenceItem(BaseModel):
    source: str = Field(description="Tool/data source name")
    fact: str = Field(
        validation_alias=AliasChoices("fact", "finding"),
        description="Concise factual finding",
    )
    ref: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ref", "reference"),
        description="Optional record ID / policy section / endpoint",
    )

    @property
    def finding(self) -> str:
        return self.fact

    @property
    def reference(self) -> str | None:
        return self.ref


class RunTelemetry(BaseModel):
    llm_calls: int | None = None
    tool_calls: int | None = None
    tool_names: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    retry_wait_ms: float = 0.0
    model_used: str | None = None
    fallback_used: bool = False
    raw_llm_recommendation: str | None = None
    raw_llm_approvals: list[str] = Field(default_factory=list)
    raw_llm_risk_flags: list[str] = Field(default_factory=list)
    code_override_applied: bool = False
    gap_justified: bool | None = None
    gap_reason: str | None = None
    injection_suspected: bool | None = None
    injection_reason: str | None = None
    ambiguity_reason: str | None = None


class ProcurementDecision(BaseModel):
    request_id: str
    recommendation: Recommendation = Field(
        description="Recommendation label: approve | reject | escalate | request_info | use_existing_tool"
    )
    evidence: list[EvidenceItem] = Field(default_factory=list)
    approvals_required: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("approvals_required", "required_approvals"),
        description="List of required approval roles",
    )
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    next_step: str
    human_review_required: bool = True
    telemetry: RunTelemetry | None = None

    @property
    def required_approvals(self) -> list[str]:
        return self.approvals_required


Architecture = Literal["single", "staged"]

# Standard Approval Roles taxonomy:
# Manager, Department Head, Procurement, Finance, CFO, Security, Privacy, Legal

# Canonical Policy Risk-Flag vocabulary (strictly enforced)
POLICY_RISK_FLAGS: set[str] = {
    "budget_insufficient",
    "conflicting_vendor_evidence",
    "existing_tool_overlap",
    "legal_review_required",
    "missing_information",
    "no_department_budget",
    "privacy_review_required",
    "prompt_injection_detected",
    "security_review_required",
    "validation_failure",
    "vendor_review_expired",
    "vendor_risk_unavailable",
}

DISALLOWED_SCHEMA_FIELDS: set[str] = {
    "internal_security_review_date",
    "security_review_date",
    "internal_review_date",
    "api_last_review_date",
    "effective_review_date",
    "security_status",
    "internal_security_status",
    "api_security_status",
    "procurement_status",
    "legal_terms_status",
    "risk_level",
    "review_age_days",
}


def filter_risk_flags(
    llm_flags: list[str],
    policy_flags: list[str],
    final_injection: bool = False,
) -> list[str]:
    """Computes final risk flags.

    Rule: Policy flags are never filtered.
    Final risk_flags = policy_check flags UNION (LLM flags INTERSECT POLICY_RISK_FLAGS),
    plus prompt_injection_detected when injection is detected.
    """
    llm_filtered = set(llm_flags) & POLICY_RISK_FLAGS
    combined_set = set(policy_flags) | llm_filtered
    if final_injection:
        combined_set.add("prompt_injection_detected")
    return sorted(list(combined_set))


def filter_llm_missing_information(
    llm_missing: list[str],
    policy_missing: list[str],
    ambiguity_reason: str | None,
) -> list[str]:
    """Combines policy missing fields with LLM fields under policy constraints.

    Rules:
    1. Base list is policy_check['missing_information'].
    2. LLM-added items are kept only if ambiguity_reason is non-empty.
    3. Invented internal schema-column names (e.g. internal_security_review_date)
       are strictly dropped.
    """
    combined = list(policy_missing)
    if ambiguity_reason and str(ambiguity_reason).strip():
        for item in llm_missing:
            clean = str(item).strip()
            if not clean:
                continue
            clean_lower = clean.lower()
            if (
                clean_lower in DISALLOWED_SCHEMA_FIELDS
                or clean_lower.endswith("_date")
                or clean_lower.endswith("_status")
                or clean_lower.startswith("internal_")
                or clean_lower.startswith("vendor_")
            ):
                continue
            if clean not in combined:
                combined.append(clean)
    return sorted(list(set(combined)))
