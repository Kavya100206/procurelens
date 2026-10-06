from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.contracts import ProcurementDecision
from src.data_access import load_employees
from src.solution import handle_request

ROOT = Path(__file__).resolve().parent
REQUESTS_FILE = ROOT / "data" / "requests.json"
REVIEWS_FILE = ROOT / "data" / "human_reviews.json"

st.set_page_config(
    page_title="ProcureLens: AI Procurement Copilot",
    page_icon="🔍",
    layout="wide",
)


def ensure_reviews_file() -> None:
    """Ensure runtime human review storage file exists."""
    if not REVIEWS_FILE.exists():
        REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
        REVIEWS_FILE.write_text("[]", encoding="utf-8")


def load_requests() -> list[dict[str, Any]]:
    if REQUESTS_FILE.exists():
        return json.loads(REQUESTS_FILE.read_text(encoding="utf-8"))
    return []


def load_reviews() -> list[dict[str, Any]]:
    ensure_reviews_file()
    try:
        return json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_review(record: dict[str, Any]) -> None:
    ensure_reviews_file()
    reviews = load_reviews()
    reviews.append(record)
    REVIEWS_FILE.write_text(json.dumps(reviews, indent=2), encoding="utf-8")


requests_data = load_requests()
requests_by_id = {r["request_id"]: r for r in requests_data}
employees_df = load_employees()

st.title("ProcureLens: AI Procurement Request Copilot")
st.caption(
    "Advisory procurement assistant evaluating budget, software catalog, vendor security status, "
    "and deterministic policy guardrails. Approvals strictly remain with human stakeholders."
)

# -----------------------------------------------------------------------------
# Sidebar: Configuration & Controls
# -----------------------------------------------------------------------------
st.sidebar.header("Configuration & Selection")

input_mode = st.sidebar.radio(
    "Request Input Mode",
    ["Select Existing Request", "Custom Request Entry"],
    index=0,
)

arch_display = st.sidebar.radio(
    "Architecture Mode",
    ["Architecture A (Single Agent)", "Architecture B (Staged 2-Agent)"],
    index=0,
)

if "Staged" in arch_display:
    st.sidebar.warning("Architecture B (Staged 2-Agent) is disabled until Phase 6.")
    selected_arch = "staged"
else:
    selected_arch = "single"

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("1. Purchase Request Details")

    if input_mode == "Select Existing Request":
        request_id = st.sidebar.selectbox(
            "Select Purchase Request",
            list(requests_by_id.keys()),
            format_func=lambda rid: f"{rid} - {requests_by_id[rid]['product_name']} (${requests_by_id[rid].get('annual_cost_usd', 0) or 0:,.0f})",
        )
        req = requests_by_id[request_id]
        emp_match = employees_df[employees_df["employee_id"] == req.get("requester_id")]
        requester_dept = emp_match.iloc[0]["department"] if not emp_match.empty else "Unknown"
        requester_name = emp_match.iloc[0]["name"] if not emp_match.empty else req.get("requester_id")

        with st.container(border=True):
            f1, f2 = st.columns(2)
            with f1:
                st.markdown(f"**Request ID:** `{req.get('request_id')}`")
                st.markdown(f"**Requester:** {requester_name} (`{req.get('requester_id')}`)")
                st.markdown(f"**Department:** {requester_dept}")
                st.markdown(f"**Product:** {req.get('product_name')}")
                st.markdown(f"**Vendor:** {req.get('vendor_name')}")
            with f2:
                cost = req.get("annual_cost_usd")
                cost_str = f"${cost:,.2f}" if cost is not None else "Missing / Not specified"
                st.markdown(f"**Annual Cost:** {cost_str}")
                st.markdown(f"**Category:** {req.get('category')}")
                st.markdown(f"**Seats / Licenses:** {req.get('user_count') or 'Not specified'}")
                st.markdown(f"**Data Access Level:** `{req.get('data_access_level')}`")
                st.markdown(f"**Urgency:** {req.get('urgency', 'normal').capitalize()}")

            integrations = req.get("requested_integrations") or []
            st.markdown(f"**Requested Integrations:** {', '.join(integrations) if integrations else 'None'}")
            st.markdown("**Business Justification:**")
            st.info(req.get("business_justification", "None provided"))

        custom_req_data = None
    else:
        # Custom Request Entry Form
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                custom_id = st.text_input("Request ID", value="REQ-CUSTOM-01")
                emp_options = [f"{r['employee_id']} - {r['name']} ({r['department']})" for _, r in employees_df.iterrows()]
                selected_emp_str = st.selectbox("Requester", emp_options)
                selected_emp_id = selected_emp_str.split(" - ")[0]
                custom_product = st.text_input("Product Name", value="Custom Enterprise App")
                custom_vendor = st.text_input("Vendor Name", value="Custom Vendor")
                custom_category = st.text_input("Category", value="General AI")

            with c2:
                custom_cost = st.number_input("Annual Cost (USD)", value=15000.0, step=1000.0)
                custom_seats = st.number_input("Seats / Licenses", value=10, step=1)
                custom_data_level = st.selectbox(
                    "Data Access Level",
                    ["internal", "internal_documents", "confidential_documents", "customer_pii", "employee_pii", "source_code", "credentials", "secrets", "none"],
                )
                custom_urgency = st.selectbox("Urgency", ["normal", "high", "urgent", "low"])
                custom_integrations = st.multiselect(
                    "Requested Integrations",
                    ["CRM", "SSO", "Git repositories", "Cloud accounts", "Document repository"],
                )

            custom_justification = st.text_area(
                "Business Justification (Untrusted input - test injections here)",
                value="Need this tool for productivity.",
            )

        request_id = custom_id
        custom_req_data = {
            "request_id": custom_id,
            "requester_id": selected_emp_id,
            "product_name": custom_product,
            "vendor_name": custom_vendor,
            "category": custom_category,
            "annual_cost_usd": custom_cost,
            "user_count": custom_seats,
            "data_access_level": custom_data_level,
            "requested_integrations": custom_integrations,
            "business_justification": custom_justification,
            "urgency": custom_urgency,
        }
        req = custom_req_data

    # Cache key for session state to prevent accidental re-runs
    session_cache_key = f"decision_{request_id}_{selected_arch}"

    # Explicit Run button: ONLY this triggers an LLM analysis
    run_clicked = st.button("Run Copilot Analysis", type="primary", use_container_width=True)

with col2:
    st.subheader("2. Copilot Recommendation & Policy Evidence")

    if run_clicked:
        if selected_arch == "staged":
            st.error("Architecture B (Staged 2-Agent) is disabled until Phase 6. Please select Architecture A.")
        else:
            with st.spinner("Analyzing request against budget, catalog, vendor security, and policy..."):
                try:
                    res = handle_request(request_id, architecture="single", request_data=custom_req_data)
                    st.session_state[session_cache_key] = res
                except Exception as exc:
                    err_text = str(exc)
                    if "429" in err_text or "rate limit" in err_text.lower():
                        st.error("Rate limit reached on Groq API (HTTP 429). Please wait a moment and retry.")
                    elif "GROQ_API_KEY" in err_text or "api_key" in err_text.lower():
                        st.error("Groq API key error. Please check GROQ_API_KEY in your .env file.")
                    else:
                        st.error(f"Analysis could not be completed: {err_text}")

    # Read from session state without re-running LLM on interactive widget clicks
    decision: ProcurementDecision | None = st.session_state.get(session_cache_key)

    if decision:
        rec = decision.recommendation
        if rec == "approve":
            st.success("### Recommendation: PROCEED TO APPROVERS (Advisory)")
            st.caption("Advisory recommendation: standard routine review meets criteria to proceed to listed business approver(s).")
        elif rec == "escalate":
            st.warning("### Recommendation: ESCALATE")
            st.caption("Requires elevated stakeholder reviews (e.g. Security, Privacy, Legal, or Finance).")
        elif rec == "request_info":
            st.info("### Recommendation: REQUEST INFORMATION")
            st.caption("Material request fields are missing or unspecified.")
        elif rec == "use_existing_tool":
            st.info("### Recommendation: USE EXISTING TOOL")
            st.caption("Internal catalog contains an existing approved alternative software.")
        else:
            st.error("### Recommendation: REJECT")
            st.caption("Action rejected (reserved strictly for human authority).")

        st.markdown(f"**Next Step:** {decision.next_step}")

        with st.container(border=True):
            r1, r2 = st.columns(2)
            with r1:
                st.markdown("**Required Approvals:**")
                if decision.approvals_required:
                    for role in decision.approvals_required:
                        st.markdown(f"- **{role}**")
                else:
                    st.markdown("None")

                st.markdown("**Missing Information:**")
                if decision.missing_information:
                    for item in decision.missing_information:
                        st.markdown(f"- ⚠️ {item}")
                else:
                    st.markdown("No missing fields detected.")

            with r2:
                st.markdown("**Risk Flags Identified:**")
                if decision.risk_flags:
                    for flag in decision.risk_flags:
                        st.markdown(f"- 🚩 `{flag}`")
                else:
                    st.markdown("None")

                st.markdown("**Human Review Status:**")
                st.markdown("🔒 Mandatory human sign-off required.")

        st.subheader("3. Grounded Tool Evidence")
        if decision.evidence:
            for i, ev in enumerate(decision.evidence, 1):
                with st.expander(f"Evidence #{i}: [{ev.source}] {ev.fact[:70]}...", expanded=True):
                    st.markdown(f"**Source:** `{ev.source}`")
                    st.markdown(f"**Fact:** {ev.fact}")
                    if ev.ref:
                        st.markdown(f"**Reference:** `{ev.ref}`")
        else:
            st.write("No evidence records available.")

        if decision.telemetry:
            tel = decision.telemetry
            retry_str = f" | Retry wait: {tel.retry_wait_ms} ms" if tel.retry_wait_ms else ""
            st.caption(
                f"Telemetry: Latency {tel.latency_ms} ms{retry_str} | LLM calls: {tel.llm_calls} | "
                f"Tool calls: {tel.tool_calls} ({', '.join(tel.tool_names)}) | "
                f"Model: {tel.model_used} (Fallback: {tel.fallback_used}) | "
                f"Code Override Applied: {tel.code_override_applied}"
            )
            if tel.gap_justified is not None or tel.injection_suspected is not None:
                st.caption(
                    f"AI Signals: Gap Justified={tel.gap_justified} (Reason: {tel.gap_reason or 'None'}) | "
                    f"Injection Suspected={tel.injection_suspected} (Reason: {tel.injection_reason or 'None'})"
                )
    else:
        st.info("Click 'Run Copilot Analysis' to evaluate this request against budget, catalog, vendor, and policy.")

st.divider()

# -----------------------------------------------------------------------------
# Section 4: Human Review Decision Panel
# -----------------------------------------------------------------------------
st.subheader("4. Human Review & Decision Recording")
st.caption(
    "Authoritative human review record. Human decisions do not overwrite stored AI outputs."
)

with st.container(border=True):
    h_col1, h_col2 = st.columns([1, 2])
    with h_col1:
        reviewer_name = st.text_input("Reviewer Name / Role", value="Procurement Lead")
        decision_action = st.selectbox(
            "Human Decision",
            ["Approve", "Reject", "Request Additional Info", "Override Recommendation"],
        )
        override_val = None
        if decision_action == "Override Recommendation":
            override_val = st.selectbox(
                "Override Target",
                ["approve", "reject", "escalate", "request_info", "use_existing_tool"],
            )

    with h_col2:
        reviewer_note = st.text_area("Reviewer Note / Justification", placeholder="Mandatory note for Reject and Override decisions...")
        submit_clicked = st.button("Submit Human Decision", type="secondary", use_container_width=True)

        if submit_clicked:
            # Rule 4: Reject and Override must require a non-empty note
            if decision_action in ["Reject", "Override Recommendation"] and not reviewer_note.strip():
                st.error("A non-empty reviewer note is strictly required for Reject and Override decisions.")
            else:
                ai_rec = decision.recommendation if decision else "Not Analyzed"
                tel_model = decision.telemetry.model_used if decision and decision.telemetry else "None"
                final_action = f"Override -> {override_val}" if decision_action == "Override Recommendation" else decision_action

                record = {
                    "request_id": request_id,
                    "ai_recommendation": ai_rec,
                    "human_decision": final_action,
                    "note": reviewer_note.strip(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "architecture": selected_arch,
                    "model_used": tel_model,
                }
                save_review(record)
                st.success(f"Human decision recorded for `{request_id}` in `data/human_reviews.json`!")

# Display review history for this request
existing_reviews = [r for r in load_reviews() if r.get("request_id") == request_id]
if existing_reviews:
    st.markdown(f"**Review History for `{request_id}`:**")
    for r in reversed(existing_reviews):
        st.markdown(
            f"- **{r.get('timestamp', '')[:19]}** by *{r.get('human_decision')}* — "
            f"\"{r.get('note', '')}\" "
            f"(AI was: `{r.get('ai_recommendation')}`, Arch: `{r.get('architecture')}`, Model: `{r.get('model_used')}`)"
        )
