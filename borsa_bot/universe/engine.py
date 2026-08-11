from __future__ import annotations

from dataclasses import dataclass

from config.models import QuoteSnapshot
from data.providers import MarketDataProvider
from indicators.engine import compute_indicators


@dataclass
class UniverseMember:
    symbol: str
    name: str
    sector: str
    eligible: bool
    reason: str
    liquidity_score: float
    spread_pct: float
    avg_volume: float
    volatility_pct: float
    pump_dump_flag: bool


def _returns(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or closes[-n - 1] == 0:
        return None
    return closes[-1] / closes[-n - 1] - 1


def detect_pump_dump(closes: list[float], volumes: list[float]) -> bool:
    """Heuristic only: abrupt price spike + volume spike without sustained follow-through."""
    if len(closes) < 20:
        return False
    r1 = closes[-1] / closes[-2] - 1 if closes[-2] else 0
    r5 = closes[-1] / closes[-6] - 1 if closes[-6] else 0
    vol_ratio = volumes[-1] / (sum(volumes[-20:-1]) / 19) if sum(volumes[-20:-1]) else 1
    # Spike day without multi-day trend support
    if abs(r1) >= 0.08 and vol_ratio >= 2.5 and abs(r5) < abs(r1) * 1.2:
        return True
    return False


def evaluate_symbol(provider: MarketDataProvider, symbol: str) -> UniverseMember:
    quote = provider.get_quote(symbol)
    bars = provider.get_bars(symbol, 220)
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    ind = compute_indicators(bars) if len(bars) >= 210 else None
    avg_vol = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0
    atr_pct = (ind.atr14 / quote.price * 100) if ind and quote.price else 99.0
    hist_ok = len(bars) >= 120
    spread_ok = quote.spread_pct <= 0.8
    liq_ok = avg_vol >= 200_000
    vol_ok = atr_pct <= 6.0
    pump = detect_pump_dump(closes, volumes)
    liq_score = min(100.0, (avg_vol / 1_000_000) * 40 + (0.8 - min(quote.spread_pct, 0.8)) / 0.8 * 40 + (10 if hist_ok else 0))
    reasons = []
    eligible = True
    if not hist_ok:
        eligible = False
        reasons.append("insufficient_history")
    if not spread_ok:
        eligible = False
        reasons.append("wide_spread")
    if not liq_ok:
        eligible = False
        reasons.append("low_liquidity")
    if not vol_ok:
        eligible = False
        reasons.append("excessive_volatility")
    if pump:
        # still eligible for watch but flagged — stricter later in alpha
        reasons.append("pump_dump_heuristic")
    if not reasons:
        reasons.append("ok")
    # Low liquidity → still may pass with reduced confidence elsewhere; hard fail if below floor
    return UniverseMember(
        symbol=symbol,
        name=quote.name,
        sector=quote.sector,
        eligible=eligible and not pump,
        reason=",".join(reasons),
        liquidity_score=round(liq_score, 1),
        spread_pct=round(quote.spread_pct, 4),
        avg_volume=round(avg_vol, 0),
        volatility_pct=round(atr_pct, 3),
        pump_dump_flag=pump,
    )


def select_universe(provider: MarketDataProvider) -> list[UniverseMember]:
    return [evaluate_symbol(provider, s) for s in provider.list_symbols()]
