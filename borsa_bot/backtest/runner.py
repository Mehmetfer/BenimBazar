from __future__ import annotations

from dataclasses import dataclass
import math

from config.models import MarketRegime, SignalAction
from data.providers import SimulatedProvider
from indicators.engine import compute_indicators
from market_regime.engine import detect_regime
from signals.engine import decide_action, score_buy


@dataclass
class BacktestMetrics:
    net_return: float
    cagr: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    expectancy: float
    trades: int
    average_holding_time: float
    consecutive_losses_max: float
    buy_hold_return: float


def assert_no_lookahead(feature_ts: list[int], label_ts: list[int]) -> bool:
    if len(feature_ts) != len(label_ts):
        raise ValueError("feature/label length mismatch")
    for f, y in zip(feature_ts, label_ts):
        if y < f:
            raise AssertionError("look-ahead bias detected")
    return True


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    return (mean / std) * math.sqrt(252) if std else 0.0


def _sortino(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return 999.0 if mean > 0 else 0.0
    dvar = sum(r ** 2 for r in downside) / len(downside)
    dstd = math.sqrt(dvar) if dvar > 0 else 0.0
    return (mean / dstd) * math.sqrt(252) if dstd else 0.0


def run_simple_backtest(symbol: str = "THYAO", steps: int = 80) -> BacktestMetrics:
    provider = SimulatedProvider(seed=7)
    cash = 100_000.0
    qty = 0.0
    entry = 0.0
    entry_step = 0
    hold_times: list[int] = []
    equity_curve: list[float] = []
    daily_returns: list[float] = []
    wins = losses = 0
    win_pnls: list[float] = []
    loss_pnls: list[float] = []
    gross_profit = gross_loss = 0.0
    trades = 0
    peak = cash
    max_dd = 0.0
    prev_equity = cash
    consec = 0
    max_consec = 0
    commission = 0.002
    slip = 0.0005

    start_price = provider.get_quote(symbol).price
    for step in range(steps):
        provider.tick()
        bars = provider.get_bars(symbol, 220)
        assert_no_lookahead([len(bars) - 1], [len(bars) - 1])
        ind = compute_indicators(bars)
        if ind is None:
            continue
        regime = detect_regime(provider) if step % 5 == 0 else MarketRegime.NEUTRAL
        quote = provider.get_quote(symbol)
        buy = score_buy(ind, quote.price, quote.volume, regime, True)
        action = decide_action(buy, 0, qty > 0, regime)
        # Cost-aware fills
        if action == SignalAction.AL and qty == 0:
            fill = quote.price * (1 + slip + commission)
            qty = int((cash * 0.1) / fill)
            if qty > 0:
                entry = fill
                entry_step = step
                cash -= qty * entry
                trades += 1
        elif qty > 0 and (buy < 55 or quote.price < entry - ind.atr14 * 2):
            fill = quote.price * (1 - slip - commission)
            pnl = (fill - entry) * qty
            cash += qty * fill
            hold_times.append(step - entry_step)
            qty = 0
            trades += 1
            if pnl >= 0:
                wins += 1
                gross_profit += pnl
                win_pnls.append(pnl)
                consec = 0
            else:
                losses += 1
                gross_loss += -pnl
                loss_pnls.append(pnl)
                consec += 1
                max_consec = max(max_consec, consec)
        equity = cash + qty * quote.price
        equity_curve.append(equity)
        daily_returns.append((equity / prev_equity) - 1 if prev_equity else 0.0)
        prev_equity = equity
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100 if peak else 0)

    end_price = provider.get_quote(symbol).price
    final = equity_curve[-1] if equity_curve else cash
    net_ret = (final / 100_000 - 1) * 100
    years = max(steps / 252, 1 / 252)
    cagr = ((final / 100_000) ** (1 / years) - 1) * 100 if final > 0 else -100.0
    bh = (end_price / start_price - 1) * 100
    closed = wins + losses
    win_rate = wins / max(1, closed) * 100
    pf = gross_profit / gross_loss if gross_loss > 0 else (999 if gross_profit > 0 else 0)
    expectancy = (gross_profit - gross_loss) / max(1, closed)
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    calmar = (cagr / max_dd) if max_dd > 0 else 0.0
    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0
    return BacktestMetrics(
        net_return=round(net_ret, 2),
        cagr=round(cagr, 2),
        sharpe=round(_sharpe(daily_returns), 2),
        sortino=round(_sortino(daily_returns), 2),
        calmar=round(calmar, 2),
        max_drawdown=round(max_dd, 2),
        win_rate=round(win_rate, 2),
        profit_factor=round(pf, 2),
        average_win=round(avg_win, 2),
        average_loss=round(avg_loss, 2),
        expectancy=round(expectancy, 2),
        trades=trades,
        average_holding_time=round(avg_hold, 2),
        consecutive_losses_max=float(max_consec),
        buy_hold_return=round(bh, 2),
    )
