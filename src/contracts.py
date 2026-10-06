from __future__ import annotations

from typing import Literal
from pydantic import AliasChoices, BaseModel, Field


class EvidenceItem(BaseModel):
    source: str = Field(description="Tool/data source name")
    finding: str = Field(
        validation_alias=AliasChoices("finding", "fact"),
        description="Concise factual finding",
    )
    reference: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reference", "ref"),
        description="Optional record ID / policy section / endpoint",
    )

    @property
    def fact(self) -> str:
        return self.finding

    @property
    def ref(self) -> str | None:
        return self.reference


class RunTelemetry(BaseModel):
    llm_calls: int | None = None
    tool_calls: int | None = None
    tool_names: list[str] = Field(default_factory=list)


class ProcurementDecision(BaseModel):
    request_id: str
    recommendation: str = Field(description="Short recommendation label or sentence")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    required_approvals: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("required_approvals", "approvals_required"),
        description="List of required approval roles",
    )
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    next_step: str
    human_review_required: bool = True
    telemetry: RunTelemetry | None = None

    @property
    def approvals_required(self) -> list[str]:
        return self.required_approvals


Architecture = Literal["single", "staged"]

# Suggested approval names for consistency in evaluation:
# Manager, Department Head, Procurement, Finance, CFO, Security, Privacy, Legal
#
# Suggested risk-flag taxonomy (you may add others):
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
