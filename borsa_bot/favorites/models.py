from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from config.models import utc_now


class FavoriteSort(str, Enum):
    AI_SCORE = "AI_SCORE"
    CONFIDENCE = "CONFIDENCE"
    PRICE_CHANGE = "PRICE_CHANGE"
    MOMENTUM = "MOMENTUM"
    EXPECTED_RETURN = "EXPECTED_RETURN"
    RISK_REWARD = "RISK_REWARD"
    SIGNAL_STRENGTH = "SIGNAL_STRENGTH"
    ALPHABETICAL = "ALPHABETICAL"
    PRIORITY = "PRIORITY"  # default AI opportunity / priority score


class ScannerClass(str, Enum):
    STRONG_OPPORTUNITY = "STRONG_OPPORTUNITY"
    OPPORTUNITY = "OPPORTUNITY"
    WAIT = "WAIT"
    RISK = "RISK"
    NO_TRADE = "NO_TRADE"


DEFAULT_GROUPS = (
    "UZUN VADELİ",
    "SWING",
    "GÜNLÜK",
    "BANKA",
    "SANAYİ",
    "TEKNOLOJİ",
    "TEMETTÜ",
    "YÜKSEK POTANSİYEL",
)


@dataclass
class PriceAlertRule:
    alert_id: str
    symbol: str
    kind: str  # ABOVE | BELOW | ENTRY_ZONE | STOP | TARGET
    threshold: float | None = None
    active: bool = True
    created_at: str = field(default_factory=lambda: utc_now().isoformat())


@dataclass
class FavoriteRecord:
    """FAVORITE ≠ PORTFOLIO. Analysis priority only — never auto-BUY boost."""

    favorite_id: str
    user_id: str
    symbol: str
    market_type: str = "BIST"  # BIST | CRYPTO — keeps markets separate
    priority: int = 50  # user watchlist priority 0-100
    notes: str = ""
    strategy_preference: list[str] = field(default_factory=lambda: ["SWING"])
    notification_preferences: dict[str, Any] = field(default_factory=dict)
    active: bool = True
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
    updated_at: str = field(default_factory=lambda: utc_now().isoformat())
    groups: list[str] = field(default_factory=list)
    last_ai_signal: str | None = None
    last_ai_confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FavoriteGroup:
    group_id: str
    user_id: str
    name: str
    created_at: str = field(default_factory=lambda: utc_now().isoformat())
