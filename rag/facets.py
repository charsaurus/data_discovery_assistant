"""
Classifies a catalog source's free-text "Access Level" field into a small
set of consistent tiers, used to power filter/facet controls in the UI
(access_level text varies per source, e.g. "Internal — Requires Manager
Approval" vs "Restricted — Requires Compliance Approval", so filtering
needs a normalized bucket, not the raw string).
"""

from __future__ import annotations

TIER_OPEN = "Open / No approval needed"
TIER_APPROVAL = "Requires Approval"
TIER_RESTRICTED = "Restricted / Compliance Required"

_TIER_ORDER = [TIER_OPEN, TIER_APPROVAL, TIER_RESTRICTED]


def classify_access_tier(access_level: str) -> str:
    text = (access_level or "").lower()
    if "no approval" in text or "already available" in text:
        return TIER_OPEN
    if "restricted" in text or "compliance" in text:
        return TIER_RESTRICTED
    if "approval" in text or "requires" in text:
        return TIER_APPROVAL
    return TIER_OPEN


def sort_tiers(tiers: list[str]) -> list[str]:
    return sorted(set(tiers), key=lambda t: _TIER_ORDER.index(t) if t in _TIER_ORDER else 99)