from typing import Any
from src.contracts import Architecture, ProcurementDecision
from src.agent_single import run_single_agent


def handle_request(
    request_id: str,
    architecture: Architecture = "single",
    request_data: dict[str, Any] | None = None,
    fixture_overlay: dict[str, Any] | None = None,
) -> ProcurementDecision:
    """Assessment adapter.

    Routes request to Architecture A (single agent) or Architecture B (staged 2-agent).
    Returns a Pydantic-validated ProcurementDecision object.
    Supports in-memory fixture_overlay for deterministic offline evaluation.
    """
    if architecture == "single":
        return run_single_agent(request_id, request_data=request_data, fixture_overlay=fixture_overlay)
    elif architecture == "staged":
        raise NotImplementedError("Architecture B (staged / 2-agent) will be implemented in Phase 6.")
    else:
        raise ValueError(f"Unknown architecture: {architecture}")
