from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta

from config.models import (
    AITradePlan,
    CapitalMode,
    EntryZone,
    FinalDecision,
    IndicatorSet,
    MarketRegime,
    OpportunityMetrics,
    PlanState,
    PlanVariant,
    TargetLevel,
    TimeHorizon,
    TradePlan,
    utc_now,
)
from config.settings import Settings, settings as default_settings
from portfolio.ledger import Position


def _r(x: float, n: int = 2) -> float:
    return round(float(x), n)


def compute_stop(
    *,
    price: float,
    ind: IndicatorSet,
    side: str = "BUY",
    cfg: Settings | None = None,
) -> tuple[float, str]:
    """ATR + support/resistance + structure — not a random percentage."""
    cfg = cfg or default_settings
    atr = max(ind.atr14, price * 0.005)
    if side == "BUY":
        atr_stop = price - atr * cfg.atr_stop_mult
        structural = ind.support * 0.998 if 0 < ind.support < price else atr_stop
        # Prefer the tighter-of-structure vs ATR-floor: use min (more protective)
        stop = min(atr_stop, structural)
        # Never place stop above price; never widen beyond 1.5*ATR*mult without structure
        floor = price - atr * cfg.atr_stop_mult * 1.35
        stop = max(stop, floor) if stop < floor else stop
        if stop >= price:
            stop = price - atr * cfg.atr_stop_mult
        reason = (
            f"Stop {_r(stop)}: ATR×{cfg.atr_stop_mult}={_r(atr_stop)}; "
            f"yapı/destek={_r(structural)}; yapı={ind.structure}; vol_ATR%={_r(atr/price*100,1)}"
        )
        return _r(stop), reason
    # SELL / short-style invalidation above
    atr_stop = price + atr * cfg.atr_stop_mult
    structural = ind.resistance * 1.002 if ind.resistance > price else atr_stop
    stop = max(atr_stop, structural)
    reason = (
        f"Invalidation {_r(stop)}: ATR×{cfg.atr_stop_mult}={_r(atr_stop)}; "
        f"direnç={_r(structural)}; yapı={ind.structure}"
    )
    return _r(stop), reason


def compute_targets(
    *,
    entry: float,
    stop: float,
    ind: IndicatorSet,
    side: str = "BUY",
    p_win: float = 0.55,
    cfg: Settings | None = None,
) -> tuple[TargetLevel, TargetLevel, TargetLevel, float]:
    cfg = cfg or default_settings
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("invalid_risk")
    if side == "BUY":
        raw = [
            entry + risk * cfg.min_risk_reward,
            entry + risk * cfg.preferred_risk_reward,
            entry + risk * max(cfg.preferred_risk_reward + 1.0, cfg.atr_take_mult),
        ]
        # Soft resistance awareness — never crush T1 below minimum R/R
        if ind.resistance > entry:
            capped = min(raw[0], max(entry + risk * cfg.min_risk_reward, ind.resistance * 0.995))
            if (capped - entry) / risk >= cfg.min_risk_reward:
                raw[0] = capped
            # else keep ATR-based T1; note resistance separately
        probs = [min(0.85, p_win + 0.05), max(0.25, p_win - 0.08), max(0.12, p_win - 0.18)]
        notes = [
            f"yakın direnç/ATR R1 (~{_r(ind.resistance)})" if ind.resistance else "ATR R1",
            "orta uzatma / preferred R",
            "geniş uzatma — düşük hit rate beklenir",
        ]
    else:
        raw = [
            entry - risk * cfg.min_risk_reward,
            entry - risk * cfg.preferred_risk_reward,
            entry - risk * max(cfg.preferred_risk_reward + 1.0, cfg.atr_take_mult),
        ]
        if 0 < ind.support < entry:
            raw[0] = max(raw[0], min(entry - risk * 1.2, ind.support * 1.005))
        probs = [min(0.85, p_win + 0.05), max(0.25, p_win - 0.08), max(0.12, p_win - 0.18)]
        notes = ["yakın destek/ATR", "orta uzatma", "geniş uzatma"]

    levels: list[TargetLevel] = []
    for price, prob, note in zip(raw, probs, notes):
        ret = (price - entry) / entry * 100 if side == "BUY" else (entry - price) / entry * 100
        levels.append(
            TargetLevel(
                price=_r(price),
                probability=round(prob, 3),
                expected_return_pct=_r(ret, 2),
                resistance_note=note,
                historical_hit_rate=None,  # no fabricated history
            )
        )
    rr = abs(levels[0].price - entry) / risk
    return levels[0], levels[1], levels[2], round(rr, 2)


def entry_zone_buy(price: float, ind: IndicatorSet, atr: float) -> EntryZone:
    half = max(atr * 0.25, price * 0.002)
    # Prefer slight pullback toward VWAP/support if nearby
    anchor = price
    if ind.vwap > 0 and abs(price - ind.vwap) / price < 0.015:
        anchor = min(price, ind.vwap)
    low = _r(anchor - half)
    high = _r(anchor + half * 0.6)
    return EntryZone(low=low, high=high, optimal=_r((low + high) / 2), label="OPTIMAL")


def breakout_trigger(price: float, ind: IndicatorSet, atr: float) -> float:
    base = max(ind.resistance, price)
    return _r(base + atr * 0.15)


def assess_chase(price: float, zone: EntryZone, atr: float) -> str | None:
    """If price ran far above entry zone, warn — do not chase."""
    if price <= zone.high * 1.005:
        return None
    dist = price - zone.high
    if dist > max(atr * 1.2, zone.high * 0.02):
        return (
            f"Fiyat giriş bölgesinden uzaklaştı ({_r(zone.low)}–{_r(zone.high)} → şu an {_r(price)}). "
            "Şu anda kovalamak riskli. Yeni setup oluşmadan AL verme."
        )
    return None


def horizon_for(strategy: str, regime: MarketRegime, atr_pct: float) -> tuple[TimeHorizon, str]:
    s = (strategy or "").upper()
    if "DAY" in s or atr_pct > 3.5:
        return TimeHorizon.DAY_TRADE, "intraday – birkaç saat / aynı gün"
    if "LONG" in s:
        return TimeHorizon.LONG_TERM, "haftalar – aylar"
    if "POSITION" in s:
        return TimeHorizon.POSITION, "birkaç hafta+"
    if regime in {MarketRegime.STRONG_BULL, MarketRegime.BULL}:
        return TimeHorizon.SWING, "3–15 işlem günü"
    return TimeHorizon.SWING, "3–10 işlem günü"


def size_from_risk(
    *,
    equity: float,
    entry: float,
    stop: float,
    size_mult: float = 1.0,
    cfg: Settings | None = None,
) -> tuple[float, float, float]:
    """Returns (qty, max_risk_tl, risk_per_share)."""
    cfg = cfg or default_settings
    risk_ps = abs(entry - stop)
    if risk_ps <= 0 or entry <= 0:
        return 0.0, 0.0, 0.0
    max_risk_tl = equity * (cfg.max_position_risk_pct / 100.0) * max(0.0, size_mult)
    qty = int(max_risk_tl / risk_ps) if max_risk_tl > 0 else 0
    return float(qty), _r(max_risk_tl, 2), _r(risk_ps, 4)


def plan_expectancy(p_win: float, reward_pct: float, loss_pct: float) -> float:
    p_loss = 1.0 - p_win
    return round(p_win * reward_pct - p_loss * loss_pct, 4)


def build_pullback_breakout_variants(
    *,
    price: float,
    ind: IndicatorSet,
    p_win: float,
    cfg: Settings | None = None,
) -> tuple[PlanVariant, PlanVariant]:
    cfg = cfg or default_settings
    atr = max(ind.atr14, price * 0.005)
    zone = entry_zone_buy(price, ind, atr)
    stop_a, reason_a = compute_stop(price=zone.optimal, ind=ind, side="BUY", cfg=cfg)
    t1a, t2a, t3a, rr_a = compute_targets(entry=zone.optimal, stop=stop_a, ind=ind, p_win=p_win, cfg=cfg)
    loss_a = abs(zone.optimal - stop_a) / zone.optimal * 100
    ev_a = plan_expectancy(p_win, t1a.expected_return_pct, loss_a)
    plan_a = PlanVariant(
        name="PULLBACK",
        entry_zone=zone,
        trigger=None,
        stop=stop_a,
        targets=[t1a, t2a, t3a],
        risk_reward=rr_a,
        expected_value=ev_a,
        confirmation="Fiyat giriş bölgesinde + hacim zayıflığı yok",
        stop_reason=reason_a,
    )

    trigger = breakout_trigger(price, ind, atr)
    # Breakout stop under breakout level / prior resistance
    stop_b = _r(max(price * 0.99, trigger - atr * 1.1))
    if stop_b >= trigger:
        stop_b = _r(trigger - atr * 0.8)
    t1b, t2b, t3b, rr_b = compute_targets(entry=trigger, stop=stop_b, ind=ind, p_win=max(0.35, p_win - 0.05), cfg=cfg)
    loss_b = abs(trigger - stop_b) / trigger * 100
    # Breakout needs volume confirmation — slight EV haircut unless volume strong
    vol_ok = ind.vol_sma20 > 0  # structural only; actual volume checked by caller via confirmation text
    ev_b = plan_expectancy(max(0.35, p_win - 0.05), t1b.expected_return_pct, loss_b) * (0.95 if vol_ok else 0.85)
    plan_b = PlanVariant(
        name="BREAKOUT",
        entry_zone=None,
        trigger=trigger,
        stop=stop_b,
        targets=[t1b, t2b, t3b],
        risk_reward=rr_b,
        expected_value=round(ev_b, 4),
        confirmation="Volume + price acceptance above trigger",
        stop_reason=f"Breakout stop under trigger: {_r(stop_b)}",
    )
    return plan_a, plan_b


def prefer_variant(a: PlanVariant, b: PlanVariant) -> str:
    # Prefer higher EV; tie-break on R/R then pullback (less chase)
    if b.expected_value > a.expected_value * 1.05 and b.risk_reward >= a.risk_reward * 0.9:
        return "BREAKOUT"
    return "PULLBACK"


def validate_plan_risk(
    *,
    rr: float,
    spread_pct: float,
    liquidity_ok: bool,
    regime: MarketRegime,
    capital_mode: CapitalMode,
    corr_ok: bool,
    qty: float,
    cfg: Settings | None = None,
) -> tuple[bool, str]:
    cfg = cfg or default_settings
    if capital_mode in {CapitalMode.KILL_SWITCH, CapitalMode.CAPITAL_PROTECTION}:
        return False, f"capital_mode={capital_mode.value}"
    if regime == MarketRegime.STRONG_BEAR:
        return False, "regime_strong_bear"
    if rr < cfg.min_risk_reward:
        return False, f"rr_below_minimum ({rr}<{cfg.min_risk_reward})"
    if spread_pct > cfg.max_spread_pct:
        return False, "spread_too_wide"
    if not liquidity_ok:
        return False, "liquidity_insufficient"
    if not corr_ok:
        return False, "portfolio_correlation"
    if qty <= 0:
        return False, "position_size_zero"
    return True, "ok"


def existing_position_advice(
    *,
    pos: Position,
    price: float,
    sell_pressure: float,
    ind: IndicatorSet,
    cfg: Settings | None = None,
) -> tuple[FinalDecision, str]:
    cfg = cfg or default_settings
    pnl_pct = (price - pos.avg_cost) / pos.avg_cost * 100 if pos.avg_cost else 0
    if pos.stop_price and price <= pos.stop_price:
        return FinalDecision.SELL_NOW, "stop seviyesine gelindi"
    if pos.target_price and price >= pos.target_price:
        return FinalDecision.PARTIAL_SELL, "hedef 1 bölgesi — kısmi kâr + trailing düşün"
    if sell_pressure >= cfg.sell_score_threshold:
        if pnl_pct > 0:
            return FinalDecision.PARTIAL_SELL, "satış baskısı + kârda — reduce"
        return FinalDecision.SELL, "satış baskısı — çıkış"
    if pnl_pct >= 6 and ind.ema9 > ind.ema21:
        return FinalDecision.TRAILING_STOP, "kârda trend devam — trailing"
    if pnl_pct < -2 and ind.ema9 < ind.ema21:
        return FinalDecision.REDUCE, "maliyet altı + zayıf momentum"
    return FinalDecision.HOLD, "pozisyon tutulabilir — yeni setup yoksa bekleyin"


def format_plan_messages(plan: AITradePlan) -> AITradePlan:
    z = plan.entry_zone
    risk_txt = "; ".join(plan.risk_notes) if plan.risk_notes else "—"
    plan.message_tr = (
        f"GÜÇLÜ AL SİNYALİ\n"
        f"Hisse: {plan.symbol}\n"
        f"Fiyat: {_r(plan.current_price)} TL\n"
        f"Önerilen giriş: {_r(z.low)} – {_r(z.high)} TL\n"
        f"Stop: {_r(plan.stop_loss)} TL\n"
        f"Hedef 1: {_r(plan.target1.price)} TL\n"
        f"Hedef 2: {_r(plan.target2.price)} TL\n"
        f"Hedef 3: {_r(plan.target3.price)} TL\n"
        f"Risk/Reward: 1:{_r(plan.risk_reward, 1)}\n"
        f"AI Confidence: {int(plan.confidence)}/100\n"
        f"Tahmini kazanma olasılığı: %{int(round(plan.win_probability * 100))}\n"
        f"Strateji: {plan.strategy}\n"
        f"Beklenen süre: {plan.holding_estimate}\n"
        f"AI gerekçesi: {plan.thesis}\n"
        f"Risk: {risk_txt}\n"
        f"{plan.disclaimer}"
    )
    if plan.side == "SELL":
        plan.message_tr = plan.message_tr.replace("GÜÇLÜ AL SİNYALİ", "SAT PLANI")

    # SMS: ASCII-ish short, avoid Turkish specials where possible
    plan.sms_ascii = (
        f"STRONG {'BUY' if plan.side == 'BUY' else 'SELL'} {plan.symbol} | "
        f"Entry {_r(z.low,1)}-{_r(z.high,1)} | SL {_r(plan.stop_loss,1)} | "
        f"TP1 {_r(plan.target1.price,1)} | TP2 {_r(plan.target2.price,1)} | "
        f"TP3 {_r(plan.target3.price,1)} | Conf {int(plan.confidence)}"
    )[:160]

    plan.push_body = (
        f"GÜÇLÜ {'AL' if plan.side == 'BUY' else 'SAT'} — {plan.symbol}\n"
        f"Giriş: {_r(z.low)}–{_r(z.high)} TL\n"
        f"Stop: {_r(plan.stop_loss)} TL\n"
        f"Hedef: {_r(plan.target1.price)} / {_r(plan.target2.price)} / {_r(plan.target3.price)}\n"
        f"R/R: {_r(plan.risk_reward, 1)}\n"
        f"Confidence: {int(plan.confidence)}"
    )

    # TTS Turkish (numeric — speech engines handle Turkish digits)
    plan.tts_tr = (
        f"{plan.symbol} için güçlü al sinyali oluştu. "
        f"Önerilen giriş {_r(z.low, 1)} ile {_r(z.high, 1)} lira arasında. "
        f"Stop {_r(plan.stop_loss, 1)} lira. "
        f"Birinci hedef {_r(plan.target1.price, 1)} lira. "
        f"Bu modelin mevcut verilere göre tahminidir. Kesin kazanç garantisi yoktur."
    )
    if plan.chase_warning:
        plan.tts_tr += " Fiyat giriş bölgesinden uzaklaştı. Kovalamak riskli."
    return plan


def build_ai_trade_plan(
    *,
    symbol: str,
    price: float,
    ind: IndicatorSet,
    decision: str,
    confidence: float,
    p_win: float,
    strategy: str,
    regime: MarketRegime,
    capital_mode: CapitalMode,
    equity: float,
    spread_pct: float,
    liquidity_ok: bool,
    corr_ok: bool = True,
    size_mult: float = 1.0,
    thesis: str = "",
    risk_notes: list[str] | None = None,
    opp: OpportunityMetrics | None = None,
    position: Position | None = None,
    sell_pressure: float = 0.0,
    cfg: Settings | None = None,
) -> AITradePlan | None:
    """
    Build full trade plan. Does NOT place orders.
    STRONG BUY only when alpha/prob/EV/risk/regime align (caller gates decision label).
    """
    cfg = cfg or default_settings
    atr = max(ind.atr14, price * 0.005)
    atr_pct = atr / price * 100
    horizon, holding = horizon_for(strategy, regime, atr_pct)
    notes = list(risk_notes or [])

    # Existing position path
    if position is not None and position.quantity > 0:
        action, why = existing_position_advice(
            pos=position, price=price, sell_pressure=sell_pressure, ind=ind, cfg=cfg
        )
        stop, stop_reason = compute_stop(price=price, ind=ind, side="BUY", cfg=cfg)
        if position.stop_price:
            stop = position.stop_price
            stop_reason = f"Mevcut pozisyon stopu: {stop}"
        zone = EntryZone(low=_r(price), high=_r(price), optimal=_r(price), label="MARK")
        t1, t2, t3, rr = compute_targets(
            entry=position.avg_cost or price,
            stop=stop,
            ind=ind,
            p_win=p_win,
            cfg=cfg,
        )
        # Prefer mark-based targets from current for sell plan
        if action in {FinalDecision.SELL, FinalDecision.SELL_NOW, FinalDecision.PARTIAL_SELL, FinalDecision.STRONG_SELL}:
            t1, t2, t3, rr = compute_targets(entry=price, stop=price + atr * cfg.atr_stop_mult, ind=ind, side="SELL", p_win=p_win, cfg=cfg)
            stop, stop_reason = compute_stop(price=price, ind=ind, side="SELL", cfg=cfg)
        qty, max_risk_tl, risk_ps = size_from_risk(
            equity=equity, entry=price, stop=stop if action == FinalDecision.HOLD else price * 0.97, size_mult=size_mult, cfg=cfg
        )
        plan = AITradePlan(
            symbol=symbol,
            side="SELL" if action in {FinalDecision.SELL, FinalDecision.SELL_NOW, FinalDecision.STRONG_SELL} else "BUY",
            current_price=_r(price),
            entry_price=_r(price),
            entry_zone=zone,
            stop_loss=stop,
            stop_reason=stop_reason,
            target1=t1,
            target2=t2,
            target3=t3,
            expected_return_pct=t1.expected_return_pct,
            maximum_risk_pct=_r(abs(price - stop) / price * 100, 2),
            risk_reward=rr,
            confidence=confidence,
            win_probability=round(p_win, 3),
            position_size=position.quantity,
            max_risk_tl=max_risk_tl,
            risk_per_share=risk_ps,
            time_horizon=horizon,
            holding_estimate=holding,
            strategy=strategy,
            state=PlanState.ACTIVE,
            final_decision=action,
            thesis=f"{why}. {thesis}".strip(),
            risk_notes=notes,
            existing_position_action=action,
            avg_cost=position.avg_cost,
            partial_tp_hint=f"T1'de %{int(cfg.tp1_exit_pct*100)} kısmi kâr",
            trailing_hint="Kalan için ATR trailing / breakeven",
            valid_until=(utc_now() + timedelta(hours=4)).isoformat(),
            invalidation_rules=[
                f"Stop/invalidation: {stop}",
                "Yeni setup yoksa planı zorlama",
            ],
        )
        ok, why_r = validate_plan_risk(
            rr=max(rr, cfg.min_risk_reward),
            spread_pct=spread_pct,
            liquidity_ok=liquidity_ok,
            regime=regime,
            capital_mode=capital_mode,
            corr_ok=corr_ok,
            qty=max(position.quantity, 1),
            cfg=cfg,
        )
        plan.risk_validated = ok
        plan.risk_reject_reason = "" if ok else why_r
        return format_plan_messages(plan)

    # Flat — build dual plans
    plan_a, plan_b = build_pullback_breakout_variants(price=price, ind=ind, p_win=p_win, cfg=cfg)
    preferred = prefer_variant(plan_a, plan_b)
    chosen = plan_a if preferred == "PULLBACK" else plan_b
    zone = plan_a.entry_zone or EntryZone(_r(price), _r(price), _r(price))
    entry = zone.optimal if preferred == "PULLBACK" else (chosen.trigger or price)
    stop = chosen.stop
    stop_reason = chosen.stop_reason
    t1, t2, t3 = chosen.targets[0], chosen.targets[1], chosen.targets[2]
    rr = chosen.risk_reward
    chase = assess_chase(price, zone, atr)

    qty, max_risk_tl, risk_ps = size_from_risk(
        equity=equity, entry=entry, stop=stop, size_mult=size_mult, cfg=cfg
    )

    # Final decision mapping — STRONG BUY only if aligned
    dec_u = (decision or "").upper()
    final = FinalDecision.WATCH
    state = PlanState.WATCH
    if chase:
        final = FinalDecision.WAIT_FOR_ENTRY
        state = PlanState.SETUP
        notes.append(chase)
    elif rr < cfg.min_risk_reward:
        final = FinalDecision.NO_TRADE
        state = PlanState.INVALIDATED
    elif dec_u in {"STRONG_BUY", "AL"} and confidence >= 80 and (opp is None or opp.expected_value > 0):
        if preferred == "BREAKOUT":
            final = FinalDecision.WAIT_FOR_ENTRY
            state = PlanState.READY
        else:
            final = FinalDecision.STRONG_BUY if confidence >= 88 and rr >= cfg.preferred_risk_reward else FinalDecision.BUY
            state = PlanState.READY
    elif dec_u in {"BUY"}:
        final = FinalDecision.BUY if not chase else FinalDecision.WAIT_FOR_ENTRY
        state = PlanState.READY if not chase else PlanState.SETUP
    elif dec_u in {"SELL", "STRONG_SELL", "SAT"}:
        final = FinalDecision.STRONG_SELL if dec_u == "STRONG_SELL" else FinalDecision.SELL
        state = PlanState.READY
    elif dec_u in {"WATCH"}:
        final = FinalDecision.WATCH
        state = PlanState.WATCH
    else:
        final = FinalDecision.NO_TRADE if dec_u in {"NO_TRADE", "ALMA"} else FinalDecision.WAIT_FOR_ENTRY
        state = PlanState.SETUP

    ok, why_r = validate_plan_risk(
        rr=rr,
        spread_pct=spread_pct,
        liquidity_ok=liquidity_ok,
        regime=regime,
        capital_mode=capital_mode,
        corr_ok=corr_ok,
        qty=qty,
        cfg=cfg,
    )
    if not ok:
        final = FinalDecision.NO_TRADE
        state = PlanState.INVALIDATED

    valid_until = (utc_now() + timedelta(hours=6 if horizon != TimeHorizon.DAY_TRADE else 2)).isoformat()
    invalidation = [
        f"Setup invalidated if price > {_r(zone.high + atr)} before entry (chase)",
        f"Stop invalidation: {stop}",
        f"VALID_UNTIL: {valid_until}",
    ]
    if preferred == "BREAKOUT" and chosen.trigger:
        invalidation.append(f"Breakout trigger: {chosen.trigger} üstü + hacim onayı")

    plan = AITradePlan(
        symbol=symbol,
        side="BUY",
        current_price=_r(price),
        entry_price=_r(entry),
        entry_zone=zone,
        stop_loss=stop,
        stop_reason=stop_reason,
        target1=t1,
        target2=t2,
        target3=t3,
        expected_return_pct=t1.expected_return_pct,
        maximum_risk_pct=_r(abs(entry - stop) / entry * 100, 2),
        risk_reward=rr,
        confidence=confidence,
        win_probability=round(p_win, 3),
        position_size=qty,
        max_risk_tl=max_risk_tl,
        risk_per_share=risk_ps,
        time_horizon=horizon,
        holding_estimate=holding,
        strategy=strategy or "ensemble",
        state=state,
        final_decision=final,
        plan_a=plan_a,
        plan_b=plan_b,
        preferred_plan=preferred,
        valid_until=valid_until,
        invalidation_rules=invalidation,
        thesis=thesis or "Trend + momentum + hacim + sektör RS birlikte değerlendirildi.",
        risk_notes=notes,
        chase_warning=chase,
        partial_tp_hint=f"T1'de %{int(cfg.tp1_exit_pct*100)} · T2 %{int(cfg.tp2_exit_pct*100)} · T3 %{int(cfg.tp3_exit_pct*100)}",
        trailing_hint=f"Kalan %{int(cfg.trail_exit_pct*100)} ATR trailing (stop asla genişlemez)",
        risk_validated=ok,
        risk_reject_reason="" if ok else why_r,
    )
    return format_plan_messages(plan)


def ai_plan_to_dict(plan: AITradePlan | None) -> dict | None:
    if plan is None:
        return None
    return asdict(plan)


def legacy_from_ai(plan: AITradePlan | None) -> TradePlan | None:
    if plan is None:
        return None
    return plan.to_legacy()
