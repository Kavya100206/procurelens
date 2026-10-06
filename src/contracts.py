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

# Standard Risk-Flag taxonomy:
# existing_tool_overlap
# budget_insufficient
# security_review_required
# privacy_review_required
# legal_review_required
# vendor_review_expired
# conflicting_vendor_evidence
# vendor_risk_unavailable
# prompt_injection_detected
# missing_information
