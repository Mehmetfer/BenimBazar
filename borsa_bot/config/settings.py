from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.example", override=False)


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Capital protection first, then positive expectancy / risk-adjusted profit."""

    mode: str = os.getenv("MODE", "PAPER").upper()
    starting_cash: float = _f("STARTING_CASH", 100_000)
    # Capital sleeves (must sum ~1.0; cash is reserve)
    long_term_capital_pct: float = _f("LONG_TERM_CAPITAL_PCT", 0.50)
    swing_capital_pct: float = _f("SWING_CAPITAL_PCT", 0.25)
    day_trading_capital_pct: float = _f("DAY_TRADING_CAPITAL_PCT", 0.10)
    cash_reserve_pct: float = _f("CASH_RESERVE_PCT", 0.15)
    max_portfolio_risk_pct: float = _f("MAX_PORTFOLIO_RISK_PCT", 1.0)
    max_position_risk_pct: float = _f("MAX_POSITION_RISK_PCT", 0.75)
    max_open_positions: int = _i("MAX_OPEN_POSITIONS", 5)
    max_sector_positions: int = _i("MAX_SECTOR_POSITIONS", 2)
    daily_max_loss_pct: float = _f("DAILY_MAX_LOSS_PCT", 2.0)
    weekly_max_loss_pct: float = _f("WEEKLY_MAX_LOSS_PCT", 5.0)
    max_drawdown_pct: float = _f("MAX_DRAWDOWN_PCT", 12.0)
    defensive_dd_pct: float = _f("DEFENSIVE_DD_PCT", 4.0)
    high_risk_dd_pct: float = _f("HIGH_RISK_DD_PCT", 7.0)
    capital_protection_dd_pct: float = _f("CAPITAL_PROTECTION_DD_PCT", 10.0)
    # Day trading hard limits
    day_max_daily_loss_pct: float = _f("DAY_MAX_DAILY_LOSS_PCT", 1.0)
    day_max_trades: int = _i("DAY_MAX_TRADES_PER_DAY", 8)
    day_max_consecutive_losses: int = _i("DAY_MAX_CONSECUTIVE_LOSSES", 3)
    day_max_position_pct: float = _f("DAY_MAX_POSITION_PCT", 5.0)
    day_max_exposure_pct: float = _f("DAY_MAX_EXPOSURE_PCT", 15.0)
    atr_stop_mult: float = _f("ATR_STOP_MULT", 2.0)
    atr_take_mult: float = _f("ATR_TAKE_MULT", 3.0)
    atr_trail_mult: float = _f("ATR_TRAIL_MULT", 2.0)
    breakeven_r_multiple: float = _f("BREAKEVEN_R_MULTIPLE", 1.0)
    min_risk_reward: float = _f("MIN_RISK_REWARD", 1.5)
    preferred_risk_reward: float = _f("PREFERRED_RISK_REWARD", 2.0)
    min_expected_value: float = _f("MIN_EXPECTED_VALUE", 0.0)
    buy_score_threshold: float = _f("BUY_SCORE_THRESHOLD", 80)
    strong_buy_threshold: float = _f("STRONG_BUY_THRESHOLD", 90)
    watch_threshold: float = _f("WATCH_THRESHOLD", 65)
    sell_score_threshold: float = _f("SELL_SCORE_THRESHOLD", 75)
    consecutive_loss_reduce: int = _i("CONSECUTIVE_LOSS_REDUCE", 3)
    consecutive_loss_pause: int = _i("CONSECUTIVE_LOSS_PAUSE", 5)
    tp1_exit_pct: float = _f("TP1_EXIT_PCT", 0.25)
    tp2_exit_pct: float = _f("TP2_EXIT_PCT", 0.25)
    tp3_exit_pct: float = _f("TP3_EXIT_PCT", 0.25)
    trail_exit_pct: float = _f("TRAIL_EXIT_PCT", 0.25)
    allow_dca: bool = _b("ALLOW_DCA", False)
    commission_pct: float = _f("COMMISSION_PCT", 0.002)
    slippage_pct: float = _f("SLIPPAGE_PCT", 0.0005)
    max_spread_pct: float = _f("MAX_SPREAD_PCT", 0.8)
    data_provider: str = os.getenv("DATA_PROVIDER", "simulated")
    kill_switch: bool = _b("KILL_SWITCH", False)
    require_manual_approval: bool = _b("REQUIRE_MANUAL_APPROVAL", True)
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = _i("API_PORT", 8090)
    db_path: Path = ROOT / "database" / "paper.db"
    log_dir: Path = ROOT / "logs"
    # Alert / notification layer (never drives trading decisions)
    sms_on: bool = _b("SMS_ON", False)
    push_on: bool = _b("PUSH_ON", True)
    sound_on: bool = _b("SOUND_ON", True)
    tts_on: bool = _b("TTS_ON", True)
    alert_cooldown_seconds: int = _i("ALERT_COOLDOWN_SECONDS", 300)
    push_enabled: bool = _b("PUSH_ENABLED", False)
    sms_provider: str = os.getenv("SMS_PROVIDER", "null")
    favorite_voice_alert: bool = _b("FAVORITE_VOICE_ALERT", True)
    favorite_scan_boost: bool = _b("FAVORITE_SCAN_BOOST", True)
    # Prediction tracking / calibration (§104) — measurement only
    prediction_model_version: str = os.getenv("PREDICTION_MODEL_VERSION", "1.0.0")
    pred_sample_insufficient: int = _i("PRED_SAMPLE_INSUFFICIENT", 50)
    pred_sample_provisional: int = _i("PRED_SAMPLE_PROVISIONAL", 100)
    pred_sample_validated: int = _i("PRED_SAMPLE_VALIDATED", 500)
    prediction_degradation_drop_pp: float = _f("PRED_DEGRADATION_DROP_PP", 10.0)
    # Daily dashboard / data integrity (§105)
    data_freshness_sec: float = _f("DATA_FRESHNESS_SEC", 30.0)
    signal_ttl_sec: float = _f("SIGNAL_TTL_SEC", 3600.0)
    daily_top_n: int = _i("DAILY_TOP_N", 8)
    allow_simulated_paper: bool = _b("ALLOW_SIMULATED_PAPER", True)

    @property
    def is_live(self) -> bool:
        return self.mode == "LIVE"


settings = Settings()

SYSTEM_OBJECTIVES = (
    "SCAN AGGRESSIVELY · ANALYZE DEEPLY · FILTER AGGRESSIVELY · TRADE SELECTIVELY · "
    "MANAGE RISK STRICTLY · LET WINNERS RUN · CUT LOSSES QUICKLY. "
    "Capital first, positive expectancy second. No profit guarantee. LIVE default OFF."
)
