from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_employees() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "employees.csv")


def load_budgets() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "department_budgets.csv")


def load_software_catalog() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "software_catalog.csv")


def load_vendors() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "vendors.csv")


def load_purchase_history() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "purchase_history.csv")
    if "annual_cost_usd" not in df.columns and "annual_amount_usd" in df.columns:
        df["annual_cost_usd"] = df["annual_amount_usd"]
    return df


def load_requests() -> list[dict]:
    return json.loads((DATA_DIR / "requests.json").read_text(encoding="utf-8"))


def get_request(request_id: str) -> dict:
    normalized_id = request_id.strip().upper()
    for request in load_requests():
        if request["request_id"].strip().upper() == normalized_id:
            return request
    raise KeyError(f"Unknown request_id: {request_id}")


def load_policy_text() -> str:
    return (DATA_DIR / "procurement_policy.md").read_text(encoding="utf-8")
