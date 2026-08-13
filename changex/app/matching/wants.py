"""Structured want / offer validation for Exchange Graph."""

from __future__ import annotations

from typing import Any

from ..value import ChangeValue, ChangeValueError, MAX_MANDAL_UNITS
from .config import KNOWN_CATEGORIES


class WantValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _as_str_list(raw: Any, *, field: str, max_items: int = 20) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise WantValidationError("INVALID_WANT", f"{field} liste olmalı")
    if len(raw) > max_items:
        raise WantValidationError("INVALID_WANT", f"{field} en fazla {max_items} öğe")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise WantValidationError("INVALID_WANT", f"{field} yalnızca string içerir")
        s = item.strip()
        if not s:
            continue
        if len(s) > 80:
            raise WantValidationError("INVALID_WANT", f"{field} öğesi çok uzun")
        out.append(s)
    return out


def validate_structured_want(
    *,
    wanted_categories: list[str] | None = None,
    wanted_subcategories: list[str] | None = None,
    wanted_brands: list[str] | None = None,
    wanted_locations: list[str] | None = None,
    wanted_value_min: int | None = None,
    wanted_value_max: int | None = None,
) -> dict[str, Any]:
    cats = _as_str_list(wanted_categories or [], field="wanted_categories")
    for c in cats:
        # Allow unknown categories (forward-compat) but reject empty garbage
        if c.lower() in {"null", "undefined"}:
            raise WantValidationError("INVALID_WANT", "geçersiz kategori")
    subs = _as_str_list(wanted_subcategories or [], field="wanted_subcategories")
    brands = _as_str_list(wanted_brands or [], field="wanted_brands")
    locs = _as_str_list(wanted_locations or [], field="wanted_locations")

    vmin = int(wanted_value_min or 0)
    vmax = int(wanted_value_max or 0)
    if vmin < 0 or vmax < 0:
        raise WantValidationError("INVALID_WANT", "değer aralığı negatif olamaz")
    if vmin > MAX_MANDAL_UNITS or vmax > MAX_MANDAL_UNITS:
        raise WantValidationError("INVALID_WANT", "değer aralığı taşması")
    if vmax and vmin and vmax < vmin:
        raise WantValidationError("INVALID_WANT", "wanted_value_max < wanted_value_min")

    return {
        "wanted_categories": cats,
        "wanted_subcategories": subs,
        "wanted_brands": brands,
        "wanted_locations": locs,
        "wanted_value_min": vmin,
        "wanted_value_max": vmax,
    }


def validate_value_tolerance(gap_tolerance: int | None) -> int:
    if gap_tolerance is None:
        return 0
    if not isinstance(gap_tolerance, int) or isinstance(gap_tolerance, bool):
        raise WantValidationError("INVALID_TOLERANCE", "value_gap_tolerance tam sayı olmalı")
    if gap_tolerance < 0:
        raise WantValidationError("INVALID_TOLERANCE", "tolerans negatif olamaz")
    if gap_tolerance > MAX_MANDAL_UNITS:
        raise WantValidationError("INVALID_TOLERANCE", "tolerans taşması")
    return gap_tolerance


def normalize_offer_fields(
    *,
    category: str,
    subcategory: str = "",
    brand: str = "",
    model_name: str = "",
    condition: str = "good",
    location: str = "",
    location_city: str = "",
    location_district: str = "",
    location_country: str = "",
    mandal_units: int,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize offer-side fields for future graph edges (no PII)."""
    if mandal_units < 0:
        raise WantValidationError("INVALID_OFFER", "mandal_units negatif olamaz")
    attrs = attributes or {}
    if not isinstance(attrs, dict):
        raise WantValidationError("INVALID_OFFER", "attributes object olmalı")
    # Strip accidental PII keys
    blocked = {"email", "phone", "address", "tc", "passport", "password", "token"}
    clean = {str(k): v for k, v in attrs.items() if str(k).lower() not in blocked}
    city = (location_city or "").strip()
    # Derive coarse city from free-text location if not set (no GPS)
    if not city and location:
        city = location.strip().split(",")[0][:80]
    return {
        "category": (category or "").strip(),
        "subcategory": (subcategory or "").strip(),
        "brand": (brand or "").strip()[:80],
        "model_name": (model_name or "").strip()[:80],
        "condition": (condition or "good").strip()[:40],
        "location": (location or "").strip()[:120],
        "location_city": city[:80],
        "location_district": (location_district or "").strip()[:80],
        "location_country": (location_country or "").strip()[:80],
        "mandal_units": int(mandal_units),
        "attributes": clean,
        "known_category": (category or "").strip() in KNOWN_CATEGORIES,
    }
