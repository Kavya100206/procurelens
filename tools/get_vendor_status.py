from __future__ import annotations

from datetime import date
from src.data_access import POLICY_REFERENCE_DATE, load_vendors
from src.vendor_client import get_vendor_risk


def _safe_parse_date(val: object) -> date | None:
    if not val or not isinstance(val, str):
        return None
    val_clean = val.strip()
    if not val_clean:
        return None
    try:
        return date.fromisoformat(val_clean)
    except (ValueError, TypeError):
        return None


def get_vendor_status(
    vendor_name: str,
    timeout_seconds: float = 3.0,
    retries: int = 2,
    fixture_overlay: dict[str, Any] | None = None,
) -> dict:
    """Vendor risk & security status tool.

    Queries both the internal procurement registry (vendors.csv) and external vendor-risk API.
    Enforces 365-day security assessment currency from fixed reference date (2026-09-30),
    detects conflicting evidence, and fails gracefully on upstream API outages.
    Supports in-memory fixture_overlay for deterministic offline testing.
    """
    clean_name = (vendor_name or "").strip()
    vendors_df = load_vendors()
    registry_match = vendors_df[vendors_df["vendor_name"].str.strip().str.lower() == clean_name.lower()]

    registry_record: dict | None = None
    if not registry_match.empty:
        registry_record = registry_match.iloc[0].to_dict()

    # Apply optional registry fixture overlay
    if fixture_overlay:
        reg_overrides = fixture_overlay.get("vendor_registry") or fixture_overlay.get("vendor_registry_overrides", {}).get(clean_name)
        if reg_overrides:
            registry_record = dict(registry_record or {})
            registry_record.update(reg_overrides)

    # Call external mock service or simulate outage/overrides
    if fixture_overlay and "vendor_api_outage" in fixture_overlay:
        outage_type = fixture_overlay["vendor_api_outage"]
        api_response = {"error": True, "detail": f"Vendor API service unavailable ({outage_type})"}
        is_api_error = True
    else:
        api_response = get_vendor_risk(clean_name, timeout_seconds=timeout_seconds, retries=retries)
        if fixture_overlay:
            risk_overrides = fixture_overlay.get("vendor_risk") or fixture_overlay.get("vendor_risk_overrides", {}).get(clean_name)
            if risk_overrides:
                if "error" in api_response:
                    api_response = {}
                api_response.update(risk_overrides)
        is_api_error = "error" in api_response

    # Parse dates safely
    reg_date_str = registry_record.get("security_review_date") if registry_record else None
    reg_date = _safe_parse_date(reg_date_str)
    api_date_str = api_response.get("last_review_date") if not is_api_error else None
    api_date = _safe_parse_date(api_date_str)

    # Use latest available date for staleness check
    effective_date = api_date or reg_date
    review_age_days = (POLICY_REFERENCE_DATE - effective_date).days if effective_date else None
    is_expired = review_age_days is not None and review_age_days > 365

    # Check for conflicts between internal registry and external service
    reg_sec_status = str(registry_record.get("security_status", "")).strip().lower() if registry_record else ""
    api_sec_status = str(api_response.get("security_review_status", "")).strip().lower() if not is_api_error else ""

    conflicting_evidence = False
    if registry_record and not is_api_error and api_sec_status:
        # Check if internal claims approved while API claims expired/not_completed, or vice-versa
        if (reg_sec_status == "approved" and api_sec_status != "approved") or (
            reg_sec_status != "approved" and api_sec_status == "approved"
        ):
            conflicting_evidence = True
        elif is_expired and reg_sec_status == "approved":
            # Registry not refreshed with latest expired review state
            conflicting_evidence = True

    # Determine vendor onboarding status
    procurement_status = str(registry_record.get("procurement_status", "New")).strip() if registry_record else "New"
    is_new_vendor = procurement_status.lower() in ["new", "pending", "unknown"]

    legal_terms_status = str(registry_record.get("legal_terms_status", "Unknown")).strip() if registry_record else "Unknown"

    return {
        "vendor_name": clean_name,
        "is_registered": registry_record is not None,
        "procurement_status": procurement_status,
        "is_new_vendor": is_new_vendor,
        "internal_security_status": registry_record.get("security_status") if registry_record else None,
        "internal_review_date": str(reg_date) if reg_date else None,
        "api_status": "error" if is_api_error else "ok",
        "api_error_detail": api_response.get("detail") if is_api_error else None,
        "api_security_status": api_sec_status if not is_api_error else None,
        "api_last_review_date": str(api_date) if api_date else None,
        "effective_review_date": str(effective_date) if effective_date else None,
        "review_age_days": review_age_days,
        "is_expired": is_expired,
        "conflicting_evidence": conflicting_evidence,
        "processes_personal_data": (
            bool(fixture_overlay["processes_personal_data"])
            if fixture_overlay and "processes_personal_data" in fixture_overlay
            else (bool(api_response.get("processes_personal_data", False)) if not is_api_error else False)
        ),
        "stores_data_outside_region": (
            bool(fixture_overlay["stores_data_outside_region"])
            if fixture_overlay and "stores_data_outside_region" in fixture_overlay
            else (bool(api_response.get("stores_data_outside_region", False)) if not is_api_error else False)
        ),
        "risk_level": api_response.get("risk_level", "unknown") if not is_api_error else "unknown",
        "legal_terms_status": legal_terms_status,
        "notes": (
            f"API unavailable: {api_response.get('detail')}"
            if is_api_error
            else registry_record.get("notes") if registry_record else api_response.get("notes", "")
        ),
    }
