"""Score band thresholds — 60–64 AL, 65+ STRONG_BUY."""

from __future__ import annotations

from config.models import CapitalMode, MarketRegime, OpportunityMetrics, ScoreBundle, SignalAction
from config.settings import Settings
from profit.ev import decide_matrix


def _scores(final: float, *, liquidity: float = 50.0) -> ScoreBundle:
    return ScoreBundle(
        technical=final,
        fundamental=50,
        market=50,
        sector=50,
        momentum=50,
        volume=50,
        news=50,
        liquidity=liquidity,
        risk=20,
        ai_confidence=60,
        final=final,
    )


def _opp() -> OpportunityMetrics:
    return OpportunityMetrics(
        p_win=0.6,
        expected_return_pct=3.0,
        expected_loss_pct=2.0,
        risk_reward=1.5,
        expected_value=1.0,
        volatility_pct=1.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=60.0,
    )


def test_score_band_60_buy_65_strong_buy():
    cfg = Settings(buy_score_threshold=60, strong_buy_threshold=65, watch_threshold=55, min_risk_reward=1.5)
    assert (
        decide_matrix(
            scores=_scores(62),
            opp=_opp(),
            owned=False,
            sell_pressure=20,
            conflict=False,
            news_block=False,
            capital_mode=CapitalMode.NORMAL,
            regime=MarketRegime.NEUTRAL,
            cfg=cfg,
        )
        == SignalAction.BUY
    )
    assert (
        decide_matrix(
            scores=_scores(67),
            opp=_opp(),
            owned=False,
            sell_pressure=20,
            conflict=False,
            news_block=False,
            capital_mode=CapitalMode.NORMAL,
            regime=MarketRegime.NEUTRAL,
            cfg=cfg,
        )
        == SignalAction.STRONG_BUY
    )
    assert (
        decide_matrix(
            scores=_scores(58),
            opp=_opp(),
            owned=False,
            sell_pressure=20,
            conflict=False,
            news_block=False,
            capital_mode=CapitalMode.NORMAL,
            regime=MarketRegime.NEUTRAL,
            cfg=cfg,
        )
        == SignalAction.WATCH
    )
