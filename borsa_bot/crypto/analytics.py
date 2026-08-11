"""Crypto technical analytics — reuses indicators.engine + technical.mtf.

Does not modify BIST strategy. Requires LIVE bars; never invents OHLCV.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from config.models import Bar, IndicatorSet, MarketRegime, QuoteSnapshot, ScoreBundle
from crypto.market import MarketType
from indicators.engine import compute_indicators
from technical.mtf import analyze_mtf, mtf_conflict_risk


CRYPTO_MTF = ("15m", "1h", "4h", "1d")
MIN_BARS_FULL = 210  # same as compute_indicators
MIN_BARS_PARTIAL = 60


@dataclass
class CryptoTechnicalSnapshot:
    symbol: str
    market_type: str = MarketType.CRYPTO.value
    ok: bool = False
    note: str = ""
    indicators: IndicatorSet | None = None
    mtf: dict[str, str] = field(default_factory=dict)
    mtf_conflict: bool = False
    mtf_penalty: float = 0.0
    mtf_note: str = ""
    mtf_aligned: bool = False
    regime: MarketRegime = MarketRegime.NEUTRAL
    scores: ScoreBundle | None = None
    model_score: float = 0.0  # 0–100 confluence score — NOT a calibrated probability
    model_score_definition: str = (
        "MODEL_SCORE: uncalibrated technical confluence 0–100 from RSI/MACD/EMA/BB/ADX/"
        "Stochastic/volume/MTF alignment. Not a win-probability %. Not calibrated."
    )
    confirmation_count: int = 0
    confirmations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "symbol": self.symbol,
            "market_type": self.market_type,
            "ok": self.ok,
            "note": self.note,
            "mtf": self.mtf,
            "mtf_conflict": self.mtf_conflict,
            "mtf_aligned": self.mtf_aligned,
            "mtf_note": self.mtf_note,
            "regime": self.regime.value,
            "model_score": self.model_score,
            "model_score_definition": self.model_score_definition,
            "confirmation_count": self.confirmation_count,
            "confirmations": self.confirmations,
            "scores": asdict(self.scores) if self.scores else None,
            "indicators": None,
        }
        if self.indicators:
            ind = self.indicators
            d["indicators"] = {
                "rsi14": ind.rsi14,
                "macd": ind.macd,
                "macd_signal": ind.macd_signal,
                "macd_hist": ind.macd_hist,
                "ema9": ind.ema9,
                "ema21": ind.ema21,
                "ema50": ind.ema50,
                "sma20": getattr(ind, "sma20", None),
                "sma50": getattr(ind, "sma50", None),
                "atr14": ind.atr14,
                "vwap": ind.vwap,
                "bb_upper": ind.bb_upper,
                "bb_mid": ind.bb_middle,
                "bb_lower": ind.bb_lower,
                "adx14": ind.adx14,
                "stoch_k": ind.stoch_k,
                "stoch_d": ind.stoch_d,
                "support": ind.support,
                "resistance": ind.resistance,
                "momentum10": ind.momentum10,
                "vol_sma20": ind.vol_sma20,
                "structure": ind.structure,
            }
        return d


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def regime_from_mtf(mtf: dict[str, str]) -> MarketRegime:
    day = mtf.get("1d")
    h4 = mtf.get("4h")
    bulls = sum(1 for x in (day, h4) if x == "BULL")
    bears = sum(1 for x in (day, h4) if x == "BEAR")
    if bulls >= 2:
        return MarketRegime.BULL if mtf.get("1h") != "BULL" else MarketRegime.STRONG_BULL
    if bears >= 2:
        return MarketRegime.BEAR if mtf.get("1h") != "BEAR" else MarketRegime.STRONG_BEAR
    return MarketRegime.NEUTRAL


def score_crypto_technicals(
    ind: IndicatorSet,
    *,
    quote: QuoteSnapshot,
    mtf: dict[str, str],
    mtf_aligned: bool,
    mtf_conflict: bool,
) -> tuple[ScoreBundle, float, list[str]]:
    """Build ScoreBundle + MODEL_SCORE from indicators. No fake probability."""
    confs: list[str] = []
    # Technical stack
    tech = 50.0
    if ind.ema9 > ind.ema21 > ind.ema50:
        tech += 18
        confs.append("ema_stack_bull")
    elif ind.ema9 < ind.ema21 < ind.ema50:
        tech -= 18
        confs.append("ema_stack_bear")
    if ind.macd_hist > 0 and ind.macd > ind.macd_signal:
        tech += 10
        confs.append("macd_bull")
    elif ind.macd_hist < 0 and ind.macd < ind.macd_signal:
        tech -= 10
        confs.append("macd_bear")
    if ind.rsi14 < 30:
        tech += 8
        confs.append("rsi_oversold")
    elif ind.rsi14 > 70:
        tech -= 8
        confs.append("rsi_overbought")
    if quote.price >= ind.bb_lower and quote.price <= ind.bb_middle:
        tech += 4
    if ind.adx14 >= 25:
        tech += 6
        confs.append("adx_trend")
    if ind.stoch_k < 20 and ind.stoch_d < 20:
        tech += 5
        confs.append("stoch_oversold")
    elif ind.stoch_k > 80 and ind.stoch_d > 80:
        tech -= 5
        confs.append("stoch_overbought")
    tech = _clamp(tech)

    momentum = _clamp(50 + ind.momentum10 * 2)
    if ind.momentum10 > 2:
        confs.append("momentum_up")
    elif ind.momentum10 < -2:
        confs.append("momentum_down")

    vol_ratio = (quote.volume / ind.vol_sma20) if ind.vol_sma20 else 1.0
    volume = _clamp(40 + min(40, (vol_ratio - 1.0) * 40))

    # Market = higher TF agreement (1h/4h/1d)
    bull_tf = sum(1 for k in ("1h", "4h", "1d") if mtf.get(k) == "BULL")
    bear_tf = sum(1 for k in ("1h", "4h", "1d") if mtf.get(k) == "BEAR")
    market = _clamp(50 + bull_tf * 12 - bear_tf * 12)
    if mtf_aligned:
        market = _clamp(market + 10)
        confs.append("mtf_aligned")
    if mtf_conflict:
        market = _clamp(market - 15)
        confs.append("mtf_conflict")

    spread = float(getattr(quote, "spread_pct", 0) or 0)
    liquidity = _clamp(90 - spread * 40)  # wide spread → low liquidity score
    atr_pct = (ind.atr14 / quote.price * 100) if quote.price else 5.0
    # risk score: higher = more dangerous (used by decide_matrix as scores.risk <= 35 for strong buy)
    risk = _clamp(20 + atr_pct * 8 + spread * 15)

    # N/A domains stay neutral — do not invent fundamental/news edge
    fundamental = 50.0
    sector = 50.0
    news = 50.0

    model_score = _clamp(
        tech * 0.35
        + momentum * 0.15
        + volume * 0.10
        + market * 0.25
        + liquidity * 0.10
        + (100 - risk) * 0.05
    )
    # ai_confidence field stores MODEL_SCORE for ScoreBundle compatibility — not P(win)
    scores = ScoreBundle(
        technical=round(tech, 1),
        fundamental=fundamental,
        market=round(market, 1),
        sector=sector,
        momentum=round(momentum, 1),
        volume=round(volume, 1),
        news=news,
        liquidity=round(liquidity, 1),
        risk=round(risk, 1),
        ai_confidence=round(model_score, 1),
        final=round(model_score, 1),
    )
    return scores, round(model_score, 1), confs


def analyze_bars(
    symbol: str,
    bars_15m: Sequence[Bar],
    quote: QuoteSnapshot,
) -> CryptoTechnicalSnapshot:
    """Run TA + MTF on 15m base bars. Insufficient history → ok=False."""
    snap = CryptoTechnicalSnapshot(symbol=symbol)
    if len(bars_15m) < MIN_BARS_FULL:
        snap.note = f"INSUFFICIENT_HISTORY need>={MIN_BARS_FULL}×15m got={len(bars_15m)}"
        # still compute light MTF labels if possible
        if len(bars_15m) >= MIN_BARS_PARTIAL:
            snap.mtf = analyze_mtf(bars_15m, base_tf_minutes=15)
        return snap

    ind = compute_indicators(bars_15m)
    if ind is None:
        snap.note = "INDICATORS_UNAVAILABLE"
        return snap

    mtf = analyze_mtf(bars_15m, base_tf_minutes=15)
    # Focus crypto MTF keys
    mtf_focus = {k: mtf.get(k, "UNAVAILABLE") for k in CRYPTO_MTF}
    conflict, penalty, note = mtf_conflict_risk(mtf)
    aligned = (not conflict) and sum(1 for k in ("1h", "4h", "1d") if mtf.get(k) == "BULL") >= 2

    scores, model_score, confs = score_crypto_technicals(
        ind,
        quote=quote,
        mtf=mtf_focus,
        mtf_aligned=aligned,
        mtf_conflict=conflict,
    )
    snap.ok = True
    snap.note = "ok"
    snap.indicators = ind
    snap.mtf = mtf_focus
    snap.mtf_conflict = conflict
    snap.mtf_penalty = penalty
    snap.mtf_note = note
    snap.mtf_aligned = aligned
    snap.regime = regime_from_mtf(mtf_focus)
    snap.scores = scores
    snap.model_score = model_score
    snap.confirmations = confs
    snap.confirmation_count = len(confs)
    return snap
