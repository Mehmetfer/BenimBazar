"""Category-agnostic listing presentation schemas (server-side evidence).

Used to enrich public listing payloads with a stable `presentation` block
and for acceptance tests. Flutter mirrors the same rules locally for UX.
"""

from __future__ import annotations

import time
from typing import Any


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _attrs(listing: dict[str, Any]) -> dict[str, str]:
    raw = listing.get("attributes") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        sv = _s(v)
        if sv:
            out[str(k).strip().upper()] = sv
    # Promote top-level brand/model into attribute map when missing
    brand = _s(listing.get("brand"))
    model = _s(listing.get("model_name"))
    if brand and "MARKA" not in out and "BRAND" not in out:
        out["MARKA"] = brand
    if model and "MODEL" not in out:
        out["MODEL"] = model
    cond = _s(listing.get("condition"))
    if cond and "DURUM" not in out and "CONDITION" not in out:
        out["DURUM"] = cond
    return out


def normalize_category(category: str | None) -> str:
    c = (_s(category) or "diğer").lower()
    aliases = {
        "araç": "vehicle",
        "arac": "vehicle",
        "otomobil": "vehicle",
        "vehicle": "vehicle",
        "mobilya": "furniture",
        "furniture": "furniture",
        "koltuk": "furniture",
        "telefon": "phone",
        "cep telefonu": "phone",
        "phone": "phone",
        "bilgisayar": "computer",
        "computer": "computer",
        "laptop": "computer",
        "elektronik": "electronics",
        "electronics": "electronics",
        "ev": "home",
        "home": "home",
        "gayrimenkul": "real_estate",
        "real_estate": "real_estate",
        "emlak": "real_estate",
        "giyim": "clothing",
        "moda": "clothing",
        "clothing": "clothing",
        "hobi": "hobby",
        "hobby": "hobby",
        "spor": "hobby",
        "diğer": "other",
        "diger": "other",
        "other": "other",
    }
    return aliases.get(c, "other")


SCHEMA_FIELDS: dict[str, list[str]] = {
    "vehicle": ["YIL", "VITES", "KM", "YAKIT", "MARKA", "MODEL", "RENK", "DURUM"],
    "furniture": ["YIL", "OTURUM", "MALZEME", "RENK", "MARKA", "DURUM", "KULLANIM"],
    "phone": ["YIL", "DEPOLAMA", "RENK", "MARKA", "MODEL", "DURUM", "GARANTI"],
    "computer": ["YIL", "RAM", "DEPOLAMA", "ISLEMCI", "MARKA", "MODEL", "DURUM"],
    "electronics": ["YIL", "BOYUT", "COZUNURLUK", "MARKA", "MODEL", "DURUM"],
    "home": ["ODA", "METREKARE", "KAT", "MARKA", "DURUM"],
    "real_estate": ["ODA", "METREKARE", "KAT", "ISINMA", "DURUM"],
    "clothing": ["BEDEN", "MARKA", "RENK", "MALZEME", "DURUM"],
    "hobby": ["MARKA", "MODEL", "DURUM", "YIL"],
    "other": ["MARKA", "MODEL", "DURUM", "YIL"],
}

HERO_KEYS: dict[str, list[str]] = {
    "vehicle": ["YIL", "VITES", "KM"],
    "furniture": ["YIL", "OTURUM", "DEGER"],
    "phone": ["YIL", "DEPOLAMA", "DURUM"],
    "computer": ["YIL", "RAM", "DEPOLAMA"],
    "electronics": ["YIL", "BOYUT", "COZUNURLUK"],
    "home": ["ODA", "METREKARE", "KAT"],
    "real_estate": ["ODA", "METREKARE", "KAT"],
    "clothing": ["BEDEN", "MARKA", "DURUM"],
    "hobby": ["MARKA", "YIL", "DURUM"],
    "other": ["MARKA", "MODEL", "DURUM"],
}

CREATE_FIELDS: dict[str, list[tuple[str, str]]] = {
    "vehicle": [
        ("YIL", "Model yılı"),
        ("VITES", "Vites"),
        ("KM", "Kilometre"),
        ("YAKIT", "Yakıt"),
        ("RENK", "Renk"),
    ],
    "furniture": [
        ("YIL", "Model yılı"),
        ("OTURUM", "Oturum / tip"),
        ("MALZEME", "Malzeme"),
        ("RENK", "Renk"),
        ("KULLANIM", "Kullanım"),
    ],
    "phone": [
        ("YIL", "Model yılı"),
        ("DEPOLAMA", "Depolama"),
        ("RENK", "Renk"),
        ("GARANTI", "Garanti"),
    ],
    "computer": [
        ("YIL", "Model yılı"),
        ("RAM", "RAM"),
        ("DEPOLAMA", "Depolama"),
        ("ISLEMCI", "İşlemci"),
    ],
    "electronics": [
        ("YIL", "Model yılı"),
        ("BOYUT", "Boyut"),
        ("COZUNURLUK", "Çözünürlük"),
    ],
    "home": [("ODA", "Oda"), ("METREKARE", "m²"), ("KAT", "Kat")],
    "real_estate": [
        ("ODA", "Oda"),
        ("METREKARE", "m²"),
        ("KAT", "Kat"),
        ("ISINMA", "Isınma"),
    ],
    "clothing": [("BEDEN", "Beden"), ("RENK", "Renk"), ("MALZEME", "Malzeme")],
    "hobby": [("YIL", "Yıl")],
    "other": [("YIL", "Yıl")],
}


def _value_label(listing: dict[str, Any]) -> str:
    value = listing.get("value") or {}
    if isinstance(value, dict):
        m = value.get("madalyon")
        if m is not None:
            return f"{m} MADALYON"
        disp = _s(value.get("display"))
        if disp:
            return disp.upper()
    mu = listing.get("mandal_units")
    if mu is not None:
        return f"{mu} MANDAL"
    return ""


def _trade_banner(listing: dict[str, Any]) -> dict[str, str]:
    status = _s(listing.get("status")).upper()
    inv = _s(listing.get("inventory_status")).upper()
    mod = _s(listing.get("moderation_status")).upper()
    if status == "TRADED" or inv == "TRADED":
        return {"code": "EXCHANGED", "label": "TAKAS EDİLMİŞTİR"}
    if status == "REJECTED" or mod == "REJECTED":
        return {"code": "REJECTED", "label": "UYGUN BULUNMADI"}
    if status in {
        "PENDING_MODERATION",
        "AI_REVIEW",
        "ADMIN_REVIEW",
        "EDIT_REQUIRED",
        "ESCALATED",
    } or mod in {"PENDING", "IN_REVIEW", "EDIT_REQUIRED"}:
        return {"code": "IN_REVIEW", "label": "İNCELEMEDE"}
    if status in {"RESERVED", "CANCELLED", "EXPIRED", "SUSPENDED"} or inv in {
        "RESERVED",
        "CANCELLED",
        "EXPIRED",
    }:
        return {"code": "CLOSED", "label": "TAKASA KAPALI"}
    return {"code": "OPEN", "label": "TAKASLARA AÇIK"}


def _format_created(listing: dict[str, Any]) -> str:
    raw = listing.get("created_at")
    try:
        ts = float(raw)
    except (TypeError, ValueError):
        return ""
    # Local calendar date in TR month names for acceptance stability
    months = [
        "Ocak",
        "Şubat",
        "Mart",
        "Nisan",
        "Mayıs",
        "Haziran",
        "Temmuz",
        "Ağustos",
        "Eylül",
        "Ekim",
        "Kasım",
        "Aralık",
    ]
    t = time.gmtime(ts)
    return f"{t.tm_mday} {months[t.tm_mon - 1]} {t.tm_year}"


def _pick(attrs: dict[str, str], keys: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for k in keys:
        v = attrs.get(k) or attrs.get(k.replace("İ", "I"))
        if not v:
            # soft aliases
            aliases = {
                "VITES": ["VİTES", "TRANSMISSION"],
                "YIL": ["YEAR", "MODEL_YEAR"],
                "DEPOLAMA": ["STORAGE", "GB"],
                "COZUNURLUK": ["ÇÖZÜNÜRLÜK", "RESOLUTION"],
                "ISLEMCI": ["İŞLEMCİ", "CPU"],
                "METREKARE": ["M2", "SQM"],
                "OTURUM": ["TIP", "TYPE", "KAPASITE"],
                "GARANTI": ["WARRANTY"],
            }
            for a in aliases.get(k, []):
                if attrs.get(a):
                    v = attrs[a]
                    break
        if v:
            rows.append({"key": k, "label": k, "value": v})
    return rows


def build_presentation(listing: dict[str, Any]) -> dict[str, Any]:
    schema = normalize_category(listing.get("category"))
    attrs = _attrs(listing)
    # Synthetic value hero for furniture-like schemas when DEGER missing
    if "DEGER" not in attrs:
        vl = _value_label(listing)
        if vl:
            attrs["DEGER"] = vl

    hero = _pick(attrs, HERO_KEYS.get(schema, HERO_KEYS["other"]))
    # Fallbacks so hero is never empty when we have brand/value
    if not hero:
        for k in ("MARKA", "MODEL", "DURUM", "DEGER"):
            if attrs.get(k):
                hero.append({"key": k, "label": k, "value": attrs[k]})
            if len(hero) >= 3:
                break

    location_parts = [
        _s(listing.get("location_city")),
        _s(listing.get("location_district")),
        _s(listing.get("location")),
    ]
    location = ", ".join(p for p in location_parts if p) or _s(listing.get("location_country"))

    preference = _s(listing.get("trade_preference")).upper() or "DIRECT_ONLY"
    delivery = {
        "DIRECT_ONLY": "DOĞRUDAN",
        "CHAIN_OK": "ZİNCİR / DOĞRUDAN",
        "CHAIN_ONLY": "ZİNCİR",
    }.get(preference, preference)

    metadata = [
        {"key": "category", "label": "KATEGORİ", "value": _s(listing.get("category")) or "—"},
        {
            "key": "subcategory",
            "label": "ALT KATEGORİ",
            "value": _s(listing.get("subcategory")) or "—",
        },
        {"key": "location", "label": "KONUM", "value": location or "—"},
        {"key": "delivery", "label": "TESLİM ŞEKLİ", "value": delivery},
    ]

    attr_keys = SCHEMA_FIELDS.get(schema, SCHEMA_FIELDS["other"])
    attribute_rows = _pick(attrs, attr_keys)
    # Append remaining attrs not already shown
    shown = {r["key"] for r in attribute_rows}
    for k, v in attrs.items():
        if k in shown or k == "DEGER":
            continue
        attribute_rows.append({"key": k, "label": k, "value": v})

    trade = _trade_banner(listing)
    return {
        "schema_id": schema,
        "title": _s(listing.get("title")),
        "hero_stats": hero,
        "trade_banner": trade,
        "metadata": metadata,
        "attribute_rows": attribute_rows,
        "description": _s(listing.get("description")),
        "contact": {
            "label": "İLETİŞİM",
            "value": "Sadece uygulama içi mesajlaşma",
            "masked_phone": "0XXX XXX XX XX",
            "note": "(Sadece uygulama içi mesajlaşma)",
        },
        "secure_trade": {
            "label": "GÜVENLİ TAKAS",
            "value": "Takaslar CHANGE X üzerinden yürütülür. Settlement/escrow henüz aktif değildir.",
        },
        "created_label": _format_created(listing),
        "create_fields": CREATE_FIELDS.get(schema, CREATE_FIELDS["other"]),
    }
