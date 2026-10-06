from __future__ import annotations

import re
from src.data_access import load_software_catalog

# Generic stop words that must never trigger category or keyword matches
STOP_WORDS = {
    "app", "apps", "software", "tool", "tools", "ai", "system", "systems",
    "user", "users", "need", "needs", "want", "wants", "new", "get", "for",
    "and", "with", "the", "this", "our", "team", "use", "enterprise", "pro",
}


def check_catalog(
    need: str,
    category: str | None = None,
    vendor_name: str | None = None,
) -> dict:
    """Deterministic software catalog tool.

    Checks internal approved software catalog for duplicate vendors, exact products,
    or category-specific tools that already solve the requested capability.
    Does not trigger false positives on generic words like 'ai' or 'app'.
    """
    df = load_software_catalog()
    matches: list[dict] = []
    need_clean = (need or "").strip()
    need_lower = need_clean.lower()
    cat_lower = (category or "").strip().lower()
    vendor_lower = (vendor_name or "").strip().lower()

    # Extract meaningful content words (length >= 4, not in stop words)
    raw_tokens = re.findall(r"\b[a-zA-Z]{3,}\b", need_lower)
    meaningful_tokens = [t for t in raw_tokens if t not in STOP_WORDS and len(t) >= 4]

    for _, row in df.iterrows():
        p_name = str(row["product_name"]).strip()
        v_name = str(row["vendor_name"]).strip()
        c_name = str(row["category"]).strip()
        notes = str(row["notes"]).strip()

        p_lower = p_name.lower()
        v_lower = v_name.lower()
        c_lower = c_name.lower()
        notes_lower = notes.lower()

        match_reasons: list[str] = []

        # 1. Exact or substantial vendor match
        if vendor_lower and (vendor_lower == v_lower or vendor_lower in v_lower or v_lower in vendor_lower):
            match_reasons.append(f"existing_vendor_{v_name}")

        # 2. Product name mentioned in request (e.g. "BrandBoard vs PixelCraft")
        if p_lower in need_lower:
            match_reasons.append(f"product_overlap_{p_name}")

        # 3. Direct category match
        if cat_lower and (cat_lower == c_lower or cat_lower in c_lower):
            match_reasons.append(f"same_category_{c_name}")

        # 4. Whole-word keyword matching against specific tool domain
        # Tokenize notes and category into distinct whole words
        row_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", f"{p_lower} {c_lower} {notes_lower}")) - STOP_WORDS
        for token in meaningful_tokens:
            if token in row_words:
                match_reasons.append(f"domain_keyword_{token}")

        if match_reasons:
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
    return {
        "query": need_clean,
        "category": category,
        "vendor_name": vendor_name,
        "has_overlap": has_overlap,
        "match_count": len(matches),
        "matches": matches,
        "message": (
            f"Found {len(matches)} existing approved tool(s) in catalog matching requirements."
            if has_overlap
            else "No existing approved tools found in catalog matching requirements."
        ),
    }
