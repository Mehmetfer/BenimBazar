"""Data source provenance — single place for tradeability & isolation rules.

Canonical kinds live in data.integrity.DataSourceKind.
This module does NOT invent market prices or enable LIVE broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Optional

from data.integrity import DataSourceKind


# --- Canonical families (Phase 2 primary + existing subtypes) ---

# Potentially tradeable ONLY for verified real-time LIVE market-data feeds.
# DELAYED ≠ LIVE (non-live). BROKER is a separate source family (not MD provider LIVE).
# SIMULATED / TEST / UNKNOWN / BACKTEST / UNAVAILABLE / REQUIRED → never tradeable.
_POTENTIALLY_TRADEABLE: frozenset[DataSourceKind] = frozenset(
    {
        DataSourceKind.LIVE,
    }
)

_NEVER_TRADEABLE: frozenset[DataSourceKind] = frozenset(
    {
        DataSourceKind.DELAYED,
        DataSourceKind.BROKER,
        DataSourceKind.SIMULATED,
        DataSourceKind.TEST,
        DataSourceKind.UNKNOWN,
        DataSourceKind.BACKTEST,
        DataSourceKind.UNAVAILABLE,
        DataSourceKind.REQUIRED,
    }
)

# Homogeneity families — DELAYED/BROKER must not mix into LIVE calculations as LIVE
_FAMILY: dict[DataSourceKind, str] = {
    DataSourceKind.LIVE: "LIVE",
    DataSourceKind.DELAYED: "DELAYED",
    DataSourceKind.BROKER: "BROKER",
    DataSourceKind.SIMULATED: "SIMULATED",
    DataSourceKind.TEST: "TEST",
    DataSourceKind.BACKTEST: "BACKTEST",
    DataSourceKind.UNKNOWN: "UNKNOWN",
    DataSourceKind.UNAVAILABLE: "UNKNOWN",
    DataSourceKind.REQUIRED: "UNKNOWN",
}

# Storage / API primary labels for UI
PRIMARY_KINDS = frozenset(
    {
        DataSourceKind.LIVE,
        DataSourceKind.SIMULATED,
        DataSourceKind.TEST,
        DataSourceKind.UNKNOWN,
        DataSourceKind.BACKTEST,
    }
)

UI_STATUS = {
    DataSourceKind.LIVE: {"glyph": "●", "label": "LIVE"},
    DataSourceKind.DELAYED: {"glyph": "◐", "label": "DELAYED (NON-LIVE)"},
    DataSourceKind.BROKER: {"glyph": "◐", "label": "BROKER (SEPARATE)"},
    DataSourceKind.SIMULATED: {"glyph": "◐", "label": "SIMULATED"},
    DataSourceKind.TEST: {"glyph": "◐", "label": "TEST"},
    DataSourceKind.BACKTEST: {"glyph": "◐", "label": "BACKTEST"},
    DataSourceKind.UNKNOWN: {"glyph": "⚠", "label": "DATA UNAVAILABLE"},
    DataSourceKind.UNAVAILABLE: {"glyph": "⚠", "label": "DATA UNAVAILABLE"},
    DataSourceKind.REQUIRED: {"glyph": "⚠", "label": "DATA UNAVAILABLE"},
}


class SourceMutationError(ValueError):
    """Raised when code tries to rewrite data_source_kind on an existing record."""


class MixedProvenanceError(ValueError):
    """Raised when LIVE + SIMULATED (or other families) mix in one calculation."""


class ClientSourceOverrideError(ValueError):
    """Frontend/API must not dictate data_source_kind."""


def parse_data_source_kind(raw: Any, *, default: DataSourceKind = DataSourceKind.UNKNOWN) -> DataSourceKind:
    """Parse to canonical DataSourceKind. Unknown strings → UNKNOWN (never invent LIVE)."""
    if isinstance(raw, DataSourceKind):
        return raw
    if raw is None:
        return default
    key = str(raw).strip().upper()
    if not key:
        return default
    aliases = {
        "SIM": DataSourceKind.SIMULATED,
        "SIMULATE": DataSourceKind.SIMULATED,
        "MOCK": DataSourceKind.SIMULATED,
        "DEMO": DataSourceKind.SIMULATED,
        "FAKE": DataSourceKind.SIMULATED,
        "SYNTHETIC": DataSourceKind.SIMULATED,
        "PAPER": DataSourceKind.SIMULATED,
        "PROD_LIVE": DataSourceKind.LIVE,
        "REAL": DataSourceKind.LIVE,
        "CI": DataSourceKind.TEST,
        "UNITTEST": DataSourceKind.TEST,
        "NONE": DataSourceKind.UNKNOWN,
        "NULL": DataSourceKind.UNKNOWN,
        "MISSING": DataSourceKind.UNKNOWN,
    }
    if key in aliases:
        return aliases[key]
    try:
        return DataSourceKind(key)
    except ValueError:
        return DataSourceKind.UNKNOWN


def provenance_family(kind: DataSourceKind | str | None) -> str:
    k = parse_data_source_kind(kind)
    return _FAMILY.get(k, "UNKNOWN")


def is_potentially_tradeable(kind: DataSourceKind | str | None) -> bool:
    """Single production rule: only LIVE-family can ever be tradeable."""
    return parse_data_source_kind(kind) in _POTENTIALLY_TRADEABLE


def is_never_tradeable(kind: DataSourceKind | str | None) -> bool:
    k = parse_data_source_kind(kind)
    return k in _NEVER_TRADEABLE or k not in _POTENTIALLY_TRADEABLE


def tradeable_flag(kind: DataSourceKind | str | None, *, verified: bool = False) -> bool:
    """Tradeable only if LIVE-family AND verified. SIMULATED/TEST/UNKNOWN → False."""
    if not is_potentially_tradeable(kind):
        return False
    return bool(verified)


def reject_source_mutation(
    current: DataSourceKind | str | None,
    proposed: DataSourceKind | str | None,
) -> None:
    """Trading pipeline must not mutate source (e.g. SIMULATED → LIVE)."""
    cur = parse_data_source_kind(current)
    prop = parse_data_source_kind(proposed)
    if cur != prop:
        raise SourceMutationError(
            f"data_source_kind immutable: cannot change {cur.value} → {prop.value}"
        )


def administrative_source_correction(
    current: DataSourceKind | str | None,
    proposed: DataSourceKind | str | None,
    *,
    allow_admin: bool,
    reason: str = "",
) -> DataSourceKind:
    """Controlled correction only — never call from trading scan/execute path."""
    if not allow_admin:
        reject_source_mutation(current, proposed)
        return parse_data_source_kind(current)
    if not reason.strip():
        raise SourceMutationError("administrative correction requires reason")
    return parse_data_source_kind(proposed)


def assert_homogeneous_provenance(
    kinds: Iterable[DataSourceKind | str | None],
    *,
    context: str = "market_data",
) -> DataSourceKind:
    """Reject mixed families (e.g. LIVE price + SIMULATED volume)."""
    families: dict[str, DataSourceKind] = {}
    for raw in kinds:
        k = parse_data_source_kind(raw)
        fam = provenance_family(k)
        families.setdefault(fam, k)
    if len(families) > 1:
        detail = ", ".join(f"{f}={k.value}" for f, k in sorted(families.items()))
        raise MixedProvenanceError(f"MIXED_PROVENANCE in {context}: {detail}")
    if not families:
        return DataSourceKind.UNKNOWN
    # Prefer the concrete kind from the single family
    return next(iter(families.values()))


def stamp_kind(obj: Any, kind: DataSourceKind | str) -> Any:
    """Attach data_source_kind onto Bar/Quote/Indicator-like objects when possible.

    Allows UNKNOWN → concrete once. Rejects SIMULATED → LIVE (etc.).
    """
    k = parse_data_source_kind(kind)
    if not hasattr(obj, "data_source_kind"):
        return obj
    existing = getattr(obj, "data_source_kind", None)
    if existing is not None and str(existing) not in {"", DataSourceKind.UNKNOWN.value}:
        reject_source_mutation(existing, k)
    try:
        setattr(obj, "data_source_kind", k.value)
    except Exception:  # noqa: BLE001
        object.__setattr__(obj, "data_source_kind", k.value)
    return obj


def kind_of(obj: Any, default: DataSourceKind = DataSourceKind.UNKNOWN) -> DataSourceKind:
    if obj is None:
        return default
    if isinstance(obj, DataSourceKind):
        return obj
    if isinstance(obj, Mapping):
        return parse_data_source_kind(
            obj.get("data_source_kind") or obj.get("market_data_source") or obj.get("kind"),
            default=default,
        )
    raw = getattr(obj, "data_source_kind", None)
    if raw is None:
        raw = getattr(obj, "kind", None)
    return parse_data_source_kind(raw, default=default)


def strip_client_source_override(payload: MutableMapping[str, Any] | None) -> MutableMapping[str, Any] | None:
    """Security: ignore client-supplied source fields — backend/provider owns provenance."""
    if payload is None:
        return None
    for key in (
        "data_source_kind",
        "market_data_source",
        "prediction_source",
        "actual_result_source",
        "kind",
        "source_kind",
        "is_live_market",
        "live_ready",
        "tradeable",
    ):
        payload.pop(key, None)
    return payload


def refuse_client_live_claim(payload: Mapping[str, Any] | None) -> None:
    """If a client tries to force LIVE, raise — do not silently accept."""
    if not payload:
        return
    for key in ("data_source_kind", "market_data_source", "kind", "source_kind"):
        if key not in payload:
            continue
        claimed = parse_data_source_kind(payload.get(key))
        if claimed in _POTENTIALLY_TRADEABLE:
            raise ClientSourceOverrideError(
                f"Client cannot set {key}={claimed.value}; source is backend-owned"
            )


def live_provider_status(*, configured: bool, connected: bool = False) -> dict[str, Any]:
    """Honest status: no real provider → NOT CONFIGURED / UNAVAILABLE."""
    if not configured:
        return {
            "live_data_provider": "NOT CONFIGURED",
            "live_data": "UNAVAILABLE",
            "data_source_kind": DataSourceKind.REQUIRED.value,
            "tradeable": False,
            "note": "Gerçek market-data provider bağlı değil. LIVE DATA UNAVAILABLE.",
        }
    if not connected:
        return {
            "live_data_provider": "CONFIGURED",
            "live_data": "UNAVAILABLE",
            "data_source_kind": DataSourceKind.REQUIRED.value,
            "tradeable": False,
            "note": "Provider yapılandırıldı ancak bağlantı yok.",
        }
    return {
        "live_data_provider": "CONFIGURED",
        "live_data": "AVAILABLE",
        "data_source_kind": DataSourceKind.LIVE.value,
        "tradeable": True,
        "note": "Doğrulanmış canlı kaynak.",
    }


def is_live_provider_configured() -> bool:
    import os

    url = os.getenv("MARKET_DATA_URL", "").strip()
    token = os.getenv("MARKET_DATA_TOKEN", "").strip()
    return bool(url and token)


def ui_status_for(kind: DataSourceKind | str | None) -> dict[str, str]:
    k = parse_data_source_kind(kind)
    base = UI_STATUS.get(k, UI_STATUS[DataSourceKind.UNKNOWN])
    return {"glyph": base["glyph"], "label": base["label"], "data_source_kind": k.value}


def provenance_payload(
    kind: DataSourceKind | str | None,
    *,
    verified: bool = False,
) -> dict[str, Any]:
    k = parse_data_source_kind(kind)
    tradeable = tradeable_flag(k, verified=verified)
    ui = ui_status_for(k)
    return {
        "data_source_kind": k.value,
        "tradeable": tradeable,
        "provenance_family": provenance_family(k),
        "ui_status": f"{ui['glyph']} {ui['label']}",
        "ui_glyph": ui["glyph"],
        "ui_label": ui["label"],
    }


def accuracy_bucket_for_source(kind: DataSourceKind | str | None) -> str:
    """LIVE / SIMULATED / TEST / BACKTEST accuracy must stay separate."""
    k = parse_data_source_kind(kind)
    fam = provenance_family(k)
    if fam == "LIVE":
        return "LIVE"
    if fam == "SIMULATED":
        return "SIMULATED"
    if fam == "TEST":
        return "TEST"
    if fam == "BACKTEST":
        return "BACKTEST"
    return "UNKNOWN"


def filter_rows_by_accuracy_bucket(rows: list[dict], bucket: str) -> list[dict]:
    want = bucket.upper()
    out = []
    for r in rows:
        src = r.get("market_data_source") or r.get("data_source_kind") or r.get("actual_result_source")
        if accuracy_bucket_for_source(src) == want:
            out.append(r)
    return out


def live_accuracy_display(rows: list[dict]) -> dict[str, Any]:
    """LIVE accuracy: never show 0% when there is no LIVE history — INSUFFICIENT DATA."""
    live_rows = filter_rows_by_accuracy_bucket(rows, "LIVE")
    if not live_rows:
        return {
            "bucket": "LIVE",
            "status": "INSUFFICIENT DATA",
            "historical_accuracy_pct": None,
            "sample_size": 0,
            "note": "Henüz ölçülecek LIVE veri yok. 0% değildir.",
        }
    hits = sum(1 for r in live_rows if r.get("direction_correct"))
    n = len(live_rows)
    return {
        "bucket": "LIVE",
        "status": "OK",
        "historical_accuracy_pct": round(hits / n * 100, 1) if n else None,
        "sample_size": n,
        "note": "LIVE-only outcomes.",
    }


@dataclass(frozen=True)
class ProvenanceSeal:
    """Immutable seal attached at record creation — no in-place kind rewrite."""

    data_source_kind: DataSourceKind
    prediction_source: DataSourceKind | None = None
    market_data_source: DataSourceKind | None = None
    actual_result_source: DataSourceKind | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_source_kind", parse_data_source_kind(self.data_source_kind))
        if self.prediction_source is not None:
            object.__setattr__(self, "prediction_source", parse_data_source_kind(self.prediction_source))
        if self.market_data_source is not None:
            object.__setattr__(self, "market_data_source", parse_data_source_kind(self.market_data_source))
        if self.actual_result_source is not None:
            object.__setattr__(self, "actual_result_source", parse_data_source_kind(self.actual_result_source))

    def mutate(self, **_kwargs: Any) -> None:
        raise SourceMutationError("ProvenanceSeal is immutable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_source_kind": self.data_source_kind.value,
            "prediction_source": self.prediction_source.value if self.prediction_source else None,
            "market_data_source": self.market_data_source.value if self.market_data_source else None,
            "actual_result_source": self.actual_result_source.value if self.actual_result_source else None,
            "tradeable": tradeable_flag(self.data_source_kind, verified=False),
        }
