"""Deterministic pair scoring — explainable components, no AI sole authority."""

from __future__ import annotations

import json
from typing import Any

from .compatibility import CategoryCompatibility, get_compatibility
from .config import MATCHING_POLICY_VERSION
from .scoring import ScoreBreakdown


MAX_OPEN = 10**18


def _loads_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            return []
    return []


def _want_categories(source: dict[str, Any]) -> list[str]:
    cats = _loads_list(source.get("wanted_categories"))
    if cats:
        return cats
    # Legacy accept_categories as structured fallback for category gate only
    return _loads_list(source.get("accept_categories"))


def structured_want_present(source: dict[str, Any]) -> bool:
    return bool(
        _loads_list(source.get("wanted_categories"))
        or _loads_list(source.get("wanted_brands"))
        or _loads_list(source.get("wanted_subcategories"))
        or int(source.get("wanted_value_min") or 0)
        or int(source.get("wanted_value_max") or 0)
    )


def free_text_want(source: dict[str, Any]) -> str:
    return str(source.get("wanted_items") or "").strip()


def value_in_tolerance(source: dict[str, Any], target: dict[str, Any]) -> bool:
    """Target HAVE value vs source WANT range + gap tolerance (integer mandal_units)."""
    target_units = int(target.get("mandal_units") or 0)
    vmin = int(source.get("wanted_value_min") or 0)
    vmax = int(source.get("wanted_value_max") or 0)
    tol = int(source.get("value_gap_tolerance") or 0)
    # Also honor listing min/max accept band if set
    min_acc = int(source.get("min_mandal_units") or 0)
    max_acc = int(source.get("max_mandal_units") or 0)

    if vmin or vmax:
        lo = max(0, vmin - tol) if vmin else 0
        hi = (vmax + tol) if vmax else MAX_OPEN
        if target_units < lo:
            return False
        if vmax and target_units > hi:
            return False
    elif min_acc or max_acc:
        lo = max(0, min_acc - tol) if min_acc else 0
        hi = (max_acc + tol) if max_acc else MAX_OPEN
        if target_units < lo:
            return False
        if max_acc and target_units > hi:
            return False
    return True


def category_compatible(
    source: dict[str, Any],
    target: dict[str, Any],
    compat: CategoryCompatibility | None = None,
) -> bool:
    compat = compat or get_compatibility()
    want_cats = _want_categories(source)
    have_cat = str(target.get("category") or "")
    if not want_cats:
        # Free-text alone does NOT open the category gate
        return False
    return any(compat.compatible(have_cat, w) for w in want_cats)


def brand_compatible(source: dict[str, Any], target: dict[str, Any]) -> bool:
    brands = [b.lower() for b in _loads_list(source.get("wanted_brands"))]
    if not brands:
        return True
    have = str(target.get("brand") or "").strip().lower()
    title = str(target.get("title") or "").lower()
    model = str(target.get("model_name") or "").lower()
    if not have and not title:
        return False
    return any(b in have or b in title or b in model for b in brands)


def location_compatible(source: dict[str, Any], target: dict[str, Any]) -> bool:
    locs = [x.lower() for x in _loads_list(source.get("wanted_locations"))]
    if not locs:
        return True
    city = str(target.get("location_city") or target.get("location") or "").lower()
    return any(loc in city or city in loc for loc in locs if loc)


def can_form_edge(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    compat: CategoryCompatibility | None = None,
) -> tuple[bool, list[str]]:
    """Deterministic edge gate: structured WANT of source vs HAVE of target."""
    reasons: list[str] = []
    sid = int(source.get("id") or 0)
    tid = int(target.get("id") or 0)
    if sid and tid and sid == tid:
        return False, ["SELF_LOOP"]
    if int(source.get("owner_id") or 0) == int(target.get("owner_id") or 0):
        return False, ["SAME_OWNER"]
    if not category_compatible(source, target, compat):
        # Free-text must not override
        if free_text_want(source) and not structured_want_present(source):
            reasons.append("FREE_TEXT_ONLY_INSUFFICIENT")
        reasons.append("CATEGORY_INCOMPATIBLE")
        return False, reasons
    if not brand_compatible(source, target):
        return False, ["BRAND_MISMATCH"]
    if not location_compatible(source, target):
        return False, ["LOCATION_MISMATCH"]
    if not value_in_tolerance(source, target):
        return False, ["VALUE_OUT_OF_TOLERANCE"]
    return True, []


class DeterministicScoreProvider:
    """ScoreProvider implementation using domain components (not AI)."""

    def __init__(self, compat: CategoryCompatibility | None = None):
        self.compat = compat or get_compatibility()
        self.policy_version = MATCHING_POLICY_VERSION

    def score_pair(self, source: dict[str, Any], target: dict[str, Any]) -> ScoreBreakdown:
        ok, _ = can_form_edge(source, target, compat=self.compat)
        if not ok:
            return ScoreBreakdown()

        want_cats = _want_categories(source)
        have_cat = str(target.get("category") or "")
        cat_scores = [self.compat.score(have_cat, w) for w in want_cats]
        category_score = max(cat_scores) if cat_scores else 0.0

        # Want score: structured brand/subcategory alignment
        want_score = 0.6
        if brand_compatible(source, target) and _loads_list(source.get("wanted_brands")):
            want_score = 1.0
        elif _loads_list(source.get("wanted_brands")):
            want_score = 0.2
        elif structured_want_present(source):
            want_score = 0.85
        elif free_text_want(source):
            # Soft signal only — never the sole gate
            ft = free_text_want(source).lower()
            blob = f"{target.get('title','')} {target.get('brand','')} {target.get('category','')}".lower()
            want_score = 0.4 if any(tok and tok in blob for tok in ft.split()[:5]) else 0.2

        # Value proximity in mandal_units
        target_units = int(target.get("mandal_units") or 0)
        vmin = int(source.get("wanted_value_min") or 0)
        vmax = int(source.get("wanted_value_max") or 0)
        if vmin or vmax:
            mid = (vmin + (vmax or vmin)) // 2 if (vmin or vmax) else target_units
            span = max(1, abs((vmax or mid) - (vmin or mid)) + int(source.get("value_gap_tolerance") or 0))
            dist = abs(target_units - mid)
            value_score = max(0.0, 1.0 - (dist / span))
        else:
            value_score = 0.7

        # Location
        if location_compatible(source, target):
            locs = _loads_list(source.get("wanted_locations"))
            location_score = 1.0 if locs else 0.5
        else:
            location_score = 0.0

        # Condition — soft preference
        cond = str(target.get("condition") or "good").lower()
        condition_score = {
            "new": 1.0,
            "like_new": 0.95,
            "good": 0.85,
            "fair": 0.6,
            "poor": 0.3,
        }.get(cond, 0.7)

        # Preference: both chain-allowed
        preference_score = 1.0 if (
            str(source.get("trade_preference") or "").upper() == "CHAIN_ALLOWED"
            and str(target.get("trade_preference") or "").upper() == "CHAIN_ALLOWED"
        ) else 0.5

        return ScoreBreakdown(
            category_score=float(category_score),
            want_score=float(want_score),
            value_score=float(value_score),
            location_score=float(location_score),
            condition_score=float(condition_score),
            preference_score=float(preference_score),
        )
