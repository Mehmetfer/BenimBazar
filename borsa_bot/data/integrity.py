"""Data integrity — never present fabricated data as live market data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Europe/Istanbul")


class DataSourceKind(str, Enum):
    """Canonical market-data provenance (Phase 2).

    Primary: LIVE | SIMULATED | TEST | UNKNOWN
    Also: DELAYED/BROKER (live-family), BACKTEST, UNAVAILABLE/REQUIRED.
    Tradeability rules live in data.provenance — do not scatter string checks.
    """

    LIVE = "LIVE"  # verified real-time market feed
    DELAYED = "DELAYED"
    BROKER = "BROKER"
    SIMULATED = "SIMULATED"  # paper / demo only — NEVER label as CANLI
    TEST = "TEST"
    UNKNOWN = "UNKNOWN"
    BACKTEST = "BACKTEST"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRED = "REQUIRED"  # config asks for live but credentials/provider missing


class FreshnessStatus(str, Enum):
    LIVE = "LIVE"  # fresh AND source is real live/broker/delayed
    FRESH_SIMULATED = "FRESH_SIMULATED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    NO_DATA = "NO_DATA"


class MarketSession(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DataSourceMeta:
    """Provenance for every critical market figure."""

    provider_id: str
    kind: DataSourceKind
    display_name: str
    connected: bool
    last_update: str | None  # ISO UTC
    age_seconds: float | None
    freshness: FreshnessStatus
    market_session: MarketSession
    is_live_market: bool  # True ONLY for verified LIVE (not DELAYED/BROKER)
    live_ready: bool  # False unless real LIVE feed + broker preflight
    note: str
    price_label: str  # e.g. "CANLI FİYAT" | "SİMÜLE FİYAT" | "VERİ YOK"

    def to_dict(self) -> dict[str, Any]:
        from data.contract import EnvironmentOrigin
        from data.provenance import provenance_payload, tradeable_flag

        d = asdict(self)
        d["kind"] = self.kind.value
        d["data_source_kind"] = self.kind.value
        d["provider"] = self.provider_id
        d["freshness"] = self.freshness.value
        d["market_session"] = self.market_session.value
        # Environment origin ≠ feed subtype
        if self.kind == DataSourceKind.SIMULATED:
            origin = EnvironmentOrigin.SIMULATED.value
        elif self.kind == DataSourceKind.TEST:
            origin = EnvironmentOrigin.TEST.value
        elif self.kind == DataSourceKind.LIVE:
            origin = EnvironmentOrigin.LIVE.value
        elif self.kind in {DataSourceKind.DELAYED, DataSourceKind.BROKER}:
            origin = EnvironmentOrigin.LIVE.value  # real-market origin, non-LIVE tradeability
        else:
            origin = EnvironmentOrigin.UNKNOWN.value
        d["environment_origin"] = origin
        d["tradeable"] = tradeable_flag(self.kind, verified=self.is_live_market)
        d.update(provenance_payload(self.kind, verified=self.is_live_market))
        return d


def bist_session_now(now: datetime | None = None) -> MarketSession:
    """Approximate BIST continuous session (Mon–Fri 10:00–18:00 Istanbul). Holidays not modeled."""
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        now = now.astimezone(IST)
    if now.weekday() >= 5:
        return MarketSession.CLOSED
    t = now.timetz().replace(tzinfo=None)
    if time(10, 0) <= t <= time(18, 0):
        return MarketSession.OPEN
    return MarketSession.CLOSED


def age_seconds(ts: datetime | None, now: datetime | None = None) -> float | None:
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds())


def build_source_meta(
    *,
    provider_id: str,
    kind: DataSourceKind,
    display_name: str,
    connected: bool,
    last_update: datetime | None,
    max_age_sec: float,
    live_ready: bool = False,
    note: str = "",
) -> DataSourceMeta:
    age = age_seconds(last_update)
    session = bist_session_now()
    # Only LIVE is live-market for trading. DELAYED ≠ LIVE. BROKER is separate.
    is_live_kind = kind == DataSourceKind.LIVE
    is_real_feed = kind in {DataSourceKind.LIVE, DataSourceKind.DELAYED, DataSourceKind.BROKER}

    if kind in {DataSourceKind.UNAVAILABLE, DataSourceKind.REQUIRED, DataSourceKind.UNKNOWN} or not connected:
        freshness = FreshnessStatus.DISCONNECTED if kind == DataSourceKind.REQUIRED else FreshnessStatus.NO_DATA
        price_label = "VERİ YOK"
        is_live = False
        default_note = (
            "DATA SOURCE REQUIRED — canlı piyasa sağlayıcısı yapılandırılmadı. "
            "Uydurma fiyat gösterilmez. LIVE DATA: UNAVAILABLE."
            if kind in {DataSourceKind.REQUIRED, DataSourceKind.UNKNOWN}
            else "Canlı veri alınamıyor."
        )
    elif age is None:
        freshness = FreshnessStatus.NO_DATA
        price_label = "VERİ YOK"
        is_live = False
        default_note = "Timestamp yok — veri yok sayılır."
    elif age > max_age_sec:
        freshness = FreshnessStatus.STALE
        price_label = "ESKİ VERİ" if is_real_feed else "SİMÜLE (ESKİ)"
        is_live = False
        default_note = f"STALE DATA — son güncelleme {int(age)} sn önce (eşik {int(max_age_sec)} sn)."
    elif kind in {DataSourceKind.SIMULATED, DataSourceKind.TEST, DataSourceKind.BACKTEST}:
        freshness = FreshnessStatus.FRESH_SIMULATED
        price_label = (
            "TEST FİYAT"
            if kind == DataSourceKind.TEST
            else ("BACKTEST" if kind == DataSourceKind.BACKTEST else "SİMÜLE FİYAT")
        )
        is_live = False
        default_note = (
            "PAPER / SİMÜLE / TEST / BACKTEST — CANLI PİYASA DEĞİL. "
            "Bu fiyatlar gerçek BIST kotasyonu değildir. NEVER TRADEABLE as LIVE."
        )
    elif kind == DataSourceKind.DELAYED:
        freshness = FreshnessStatus.LIVE  # fresh delayed feed, but NOT live-tradeable
        price_label = "GECİKMELİ FİYAT"
        is_live = False  # DELAYED ≠ LIVE
        default_note = "DELAYED feed — NON-LIVE for trading signals."
    elif kind == DataSourceKind.BROKER:
        freshness = FreshnessStatus.LIVE
        price_label = "BROKER FİYAT"
        is_live = False  # BROKER ≠ market-data LIVE provider
        default_note = "BROKER source — SEPARATE from market-data provider LIVE."
    else:
        # LIVE only
        freshness = FreshnessStatus.LIVE
        price_label = "CANLI FİYAT"
        is_live = bool(is_live_kind)
        default_note = "Doğrulanmış canlı piyasa kaynağı."

    # Never claim live_ready without real LIVE feed (+ broker preflight later)
    ready = bool(live_ready and is_live_kind and is_live and connected)
    return DataSourceMeta(
        provider_id=provider_id,
        kind=kind,
        display_name=display_name,
        connected=connected and kind not in {DataSourceKind.UNAVAILABLE, DataSourceKind.REQUIRED},
        last_update=last_update.astimezone(timezone.utc).isoformat() if last_update else None,
        age_seconds=round(age, 1) if age is not None else None,
        freshness=freshness,
        market_session=session,
        is_live_market=is_live,
        live_ready=ready,
        note=note or default_note,
        price_label=price_label,
    )


def format_age_tr(age: float | None) -> str:
    if age is None:
        return "—"
    if age < 2:
        return "az önce"
    if age < 60:
        return f"{int(age)} sn önce"
    if age < 3600:
        return f"{int(age // 60)} dk önce"
    return f"{int(age // 3600)} sa önce"
