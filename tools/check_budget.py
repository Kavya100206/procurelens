from __future__ import annotations

from src.data_access import load_budgets


def check_budget(department: str, amount: float | int | None) -> dict:
    """Deterministic budget tool.

    Compares requested annualized cost with available department software budget.
    Implements policy rules for unmapped departments (e.g. Go To Market).
    """
    df = load_budgets()

    # Normalize department for case-insensitive lookup
    dept_clean = department.strip() if department else ""
    matches = df[df["department"].str.strip().str.lower() == dept_clean.lower()]

    if matches.empty:
        return {
            "department": department,
            "amount": amount,
            "budget_status": "no_budget_record",
            "available_budget": None,
            "annual_budget": None,
            "committed_budget": None,
            "is_sufficient": False,
            "shortfall": None,
            "message": f"No budget record found for department '{department}'.",
        }

    row = matches.iloc[0]
    annual_budget = float(row["annual_software_budget_usd"])
    committed_budget = float(row["committed_usd"])
    available_budget = float(row["available_usd"])

    if amount is None:
        return {
            "department": row["department"],
            "amount": None,
            "budget_status": "missing_amount",
            "available_budget": available_budget,
            "annual_budget": annual_budget,
            "committed_budget": committed_budget,
            "is_sufficient": None,
            "shortfall": None,
            "message": f"Requested amount is missing or unspecified for {row['department']}.",
        }

    cost = float(amount)
    is_sufficient = cost <= available_budget
    shortfall = max(0.0, cost - available_budget)

    return {
        "department": row["department"],
        "amount": cost,
        "budget_status": "sufficient" if is_sufficient else "exceeded",
        "available_budget": available_budget,
        "annual_budget": annual_budget,
        "committed_budget": committed_budget,
        "is_sufficient": is_sufficient,
        "shortfall": shortfall,
        "message": (
            f"Department '{row['department']}' has sufficient budget (${available_budget:,.2f} available for ${cost:,.2f} request)."
            if is_sufficient
            else f"Budget exceeded for '{row['department']}': requested ${cost:,.2f} but only ${available_budget:,.2f} available (shortfall: ${shortfall:,.2f})."
        ),
    }
