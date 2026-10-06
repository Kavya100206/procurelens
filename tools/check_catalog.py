from __future__ import annotations

from typing import Any
import pandas as pd
from src.data_access import load_software_catalog


def check_catalog(
    category: str | None = None,
    vendor_name: str | None = None,
    product_name: str | None = None,
    need: str | None = None,  # retained for backward compatibility but ignored for matching
    fixture_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic software catalog tool.

    Checks internal approved software catalog exclusively using structured request fields
    (category, vendor_name, product_name). Free-text justification is explicitly IGNORED
    for matching to prevent prompt injection or adversarial text manipulation.

    Overlap classification:
    - "same_product_expansion": requested product/vendor matches an existing catalog tool
    - "alternative_product_overlap": different vendor/product in the same approved category
    - "none": no matching catalog product or category
    """
    df = load_software_catalog()

    # Apply optional catalog fixture overlay if provided
    if fixture_overlay and "catalog_items" in fixture_overlay:
        overlay_rows = fixture_overlay["catalog_items"]
        if overlay_rows:
            df = pd.concat([df, pd.DataFrame(overlay_rows)], ignore_index=True)

    matches: list[dict[str, Any]] = []
    cat_clean = (category or "").strip()
    cat_lower = cat_clean.lower()
    vendor_clean = (vendor_name or "").strip()
    vendor_lower = vendor_clean.lower()
    prod_clean = (product_name or "").strip()
    prod_lower = prod_clean.lower()

    overlap_type = "none"
    matched_product: str | None = None

    for _, row in df.iterrows():
        p_name = str(row["product_name"]).strip()
        v_name = str(row["vendor_name"]).strip()
        c_name = str(row["category"]).strip()
        notes = str(row["notes"]).strip()

        p_lower = p_name.lower()
        v_lower = v_name.lower()
        c_lower = c_name.lower()

        is_same_vendor_or_product = False
        is_same_category = False
        match_reasons: list[str] = []

        # 1. Exact or substantial vendor/product match (structured fields only)
        if vendor_lower and (vendor_lower == v_lower or vendor_lower in v_lower or v_lower in vendor_lower):
            is_same_vendor_or_product = True
            match_reasons.append(f"existing_vendor_{v_name}")
        if prod_lower and (prod_lower == p_lower or prod_lower in p_lower or p_lower in prod_lower):
            is_same_vendor_or_product = True
            match_reasons.append(f"existing_product_{p_name}")

        # 2. Category match (structured category field only)
        if cat_lower and (cat_lower == c_lower or cat_lower in c_lower or c_lower in cat_lower):
            is_same_category = True
            match_reasons.append(f"same_category_{c_name}")

        if is_same_vendor_or_product or is_same_category:
            matches.append(
                {
                    "software_id": row["software_id"],
                    "product_name": p_name,
                    "vendor_name": v_name,
                    "category": c_name,
                    "status": row["status"],
                    "annual_cost_usd": float(row["annual_cost_usd"]),
                    "licensed_seats": int(row["licensed_seats"]),
                    "scope": row["scope"],
                    "notes": notes,
                    "reasons": sorted(list(set(match_reasons))),
                }
            )

    has_overlap = len(matches) > 0
    if has_overlap:
        # Determine overlap classification
        has_same_product = any(
            (vendor_lower and (vendor_lower in m["vendor_name"].lower() or m["vendor_name"].lower() in vendor_lower))
            or (prod_lower and (prod_lower in m["product_name"].lower() or m["product_name"].lower() in prod_lower))
            for m in matches
        )
        if has_same_product:
            overlap_type = "same_product_expansion"
            matched_product = matches[0]["product_name"]
        else:
            overlap_type = "alternative_product_overlap"
            matched_product = matches[0]["product_name"]

    return {
        "has_overlap": has_overlap,
        "overlap_type": overlap_type,
        "matched_product": matched_product,
        "match_count": len(matches),
        "matches": matches,
        "category": category,
        "vendor_name": vendor_name,
        "product_name": product_name,
        "justification_text_ignored_for_matching": None,
        "message": (
            f"Found {len(matches)} existing approved tool(s) in catalog: {overlap_type} ({matched_product or 'None'})."
            if has_overlap
            else "No existing approved tools found in catalog matching requirements."
        ),
    }
