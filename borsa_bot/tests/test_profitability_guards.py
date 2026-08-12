"""Profitability / cost / loss-attribution tests — no fabricated metrics."""

from __future__ import annotations

import tempfile
from pathlib import Path

from config.models import CapitalMode, MarketRegime, OpportunityMetrics, ScoreBundle, SignalAction
from config.settings import settings
from profit.costs import edge_covers_cost, net_expectancy_pct, round_trip_cost_pct
from profit.diagnostics import analyze_paper_ledger
from profit.ev import decide_matrix


def _scores(final: float = 62.0) -> ScoreBundle:
    return ScoreBundle(
        technical=60,
        fundamental=50,
        market=60,
        sector=50,
        momentum=60,
        volume=60,
        news=50,
        liquidity=60,
        risk=30,
        ai_confidence=55,
        final=final,
    )


def test_round_trip_cost_positive():
    cost = round_trip_cost_pct()
    assert cost > 0
    assert abs(cost - 0.5) < 1e-6  # 2*(0.2%+0.05%)


def test_net_expectancy_subtracts_costs():
    assert net_expectancy_pct(1.0) == round(1.0 - round_trip_cost_pct(), 4)
    assert net_expectancy_pct(0.4) < 0


def test_no_trade_when_edge_below_cost():
    """Net EV <= 0 ⇒ NO_TRADE (edge wiped by commission+slippage)."""
    opp = OpportunityMetrics(
        p_win=0.55,
        expected_return_pct=0.3,
        expected_loss_pct=1.0,
        risk_reward=0.3,
        expected_value=-0.2,  # already net-negative after costs
        volatility_pct=2.0,
        drawdown_impact=0.5,
        position_size_mult=1.0,
        confidence=55.0,
    )
    assert not edge_covers_cost(opp.expected_value)
    decision = decide_matrix(
        scores=_scores(62),
        opp=opp,
        owned=False,
        sell_pressure=10,
        conflict=False,
        news_block=False,
        capital_mode=CapitalMode.NORMAL,
        regime=MarketRegime.NEUTRAL,
    )
    assert decision == SignalAction.NO_TRADE


def test_loss_attribution_from_temp_ledger():
    from portfolio.ledger import PortfolioLedger

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "paper.db"
        led = PortfolioLedger(db_path=db)
        led.apply_buy("THYAO", "Havacılık", 10, 100.0, "b1", 95.0, 110.0)
        led.apply_sell("THYAO", 10, 97.0, "s1")
        report = analyze_paper_ledger(db)
        assert report.closed_rounds == 1
        assert report.realized_pnl < 0
        assert report.profitability_status == "PROFITABILITY_UNPROVEN"
        assert report.losers == 1


def test_follow_blocked_on_simulated(monkeypatch):
    from dataclasses import replace

    from config.settings import settings as root_settings
    from portfolio.ledger import PortfolioLedger
    import strategy.service as svc_mod
    from strategy.service import TradingService

    with tempfile.TemporaryDirectory() as tmp:
        svc = TradingService()
        svc.ledger = PortfolioLedger(db_path=Path(tmp) / "p.db")
        svc.broker.ledger = svc.ledger
        monkeypatch.setattr(
            svc_mod,
            "settings",
            replace(root_settings, bist_paper_auto_follow=True, data_provider="simulated"),
        )

        class Meta:
            kind = type("K", (), {"value": "SIMULATED"})()

        monkeypatch.setattr(svc.provider, "source_meta", lambda *_a, **_k: Meta())
        monkeypatch.setattr(svc, "monitor_exits", lambda: [])
        monkeypatch.setattr(svc, "paper_wallet", lambda: {"cash": 100000})
        svc.provider.provider_id = "simulated"
        out = svc.follow_recommendations(max_buys=1)
        assert out.get("ok") is False
        assert out.get("skipped") == "SIMULATED_DATA_NO_AUTO_TRADE"
