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

    # APP_ENV: PRODUCTION | DEVELOPMENT | TEST (aliases: PROD/DEV/CI)
    app_env: str = os.getenv("APP_ENV", os.getenv("ENV", "DEVELOPMENT")).upper()
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
    min_expected_value: float = _f("MIN_EXPECTED_VALUE", 0.0)  # compared to NET EV (after round-trip costs)
    buy_score_threshold: float = _f("BUY_SCORE_THRESHOLD", 60)
    strong_buy_threshold: float = _f("STRONG_BUY_THRESHOLD", 65)
    watch_threshold: float = _f("WATCH_THRESHOLD", 55)
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
    # auto = Yahoo BIST when session OPEN, simulated only when CLOSED (paper)
    data_provider: str = os.getenv("DATA_PROVIDER", "auto")
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
    # Market-data contract foundation (Phase 3 readiness — no real provider yet)
    base_timeframe: str = os.getenv("BASE_TIMEFRAME", "15m")
    required_history_bars: int = _i("REQUIRED_HISTORY_BARS", 240)
    # CRYPTO / Paribu foundation — default OFF; BIST path unchanged
    crypto_enabled: bool = _b("CRYPTO_ENABLED", False)
    # auto = OKX→Gate→Kraken public REST (ccxt-style); paribu optional
    crypto_provider: str = os.getenv("CRYPTO_PROVIDER", "auto")
    crypto_failover: str = os.getenv("CRYPTO_FAILOVER", "okx,gate,kraken")
    paribu_enabled: bool = _b("PARIBU_ENABLED", False)
    paribu_api_base: str = os.getenv("PARIBU_API_BASE", "https://api.paribu.com")
    paribu_api_key: str = os.getenv("PARIBU_API_KEY", "")
    paribu_api_secret: str = os.getenv("PARIBU_API_SECRET", "")
    paribu_ws_enabled: bool = _b("PARIBU_WS_ENABLED", True)
    paribu_poll_interval_sec: float = _f("PARIBU_POLL_INTERVAL_SEC", 3.0)
    # Phase 3 crypto analytics / signals (still paper-only; no live broker)
    crypto_signals_enabled: bool = _b("CRYPTO_SIGNALS_ENABLED", False)
    crypto_predictions_enabled: bool = _b("CRYPTO_PREDICTIONS_ENABLED", True)
    crypto_max_exposure_pct: float = _f("CRYPTO_MAX_EXPOSURE_PCT", 15.0)
    crypto_atr_cap_pct: float = _f("CRYPTO_ATR_CAP_PCT", 8.0)
    crypto_scan_max_symbols: int = _i("CRYPTO_SCAN_MAX_SYMBOLS", 40)
    crypto_paper_trading_enabled: bool = _b("CRYPTO_PAPER_TRADING_ENABLED", False)
    # Phase 6–7 autonomy
    user_trading_mode: str = os.getenv("USER_TRADING_MODE", "PAPER").upper()
    autonomy_enabled: bool = _b("AUTONOMY_ENABLED", True)
    autonomous_mode: bool = _b("AUTONOMOUS_MODE", True)  # alias of autonomy_enabled
    autonomy_deep_max: int = _i("AUTONOMY_DEEP_MAX", 40)
    autonomy_scan_cooldown_seconds: float = _f("AUTONOMY_SCAN_COOLDOWN_SECONDS", 25.0)
    autonomy_idempotency_minutes: int = _i("AUTONOMY_IDEMPOTENCY_MINUTES", 15)
    # Execution venue: PAPER | SHADOW | LIVE (default PAPER — safe)
    execution_mode: str = os.getenv("EXECUTION_MODE", "PAPER").upper()
    # Hard lock for real broker — even EXECUTION_MODE=LIVE stays blocked when false
    live_broker_enabled: bool = _b("LIVE_BROKER_ENABLED", False)
    live_confirmation_required: bool = _b("LIVE_CONFIRMATION_REQUIRED", True)
    live_confirmed: bool = _b("LIVE_CONFIRMED", False)  # explicit human confirmation
    # Live foundation (infra only — no money until adapter implemented + unlocked)
    live_broker_adapter: str = os.getenv("LIVE_BROKER_ADAPTER", "disabled").strip().lower()
    live_dry_run: bool = _b("LIVE_DRY_RUN", True)  # keep true until micro-live acceptance
    live_broker_base_url: str = os.getenv("LIVE_BROKER_BASE_URL", "")
    live_broker_api_key: str = os.getenv("LIVE_BROKER_API_KEY", "")
    live_broker_api_secret: str = os.getenv("LIVE_BROKER_API_SECRET", "")
    live_broker_account_id: str = os.getenv("LIVE_BROKER_ACCOUNT_ID", "")
    # Paper FSM
    paper_partial_fill_pct: float = _f("PAPER_PARTIAL_FILL_PCT", 1.0)
    paper_cancel_race_fill_pct: float = _f("PAPER_CANCEL_RACE_FILL_PCT", 0.0)
    block_orders_when_market_closed: bool = _b("BLOCK_ORDERS_WHEN_MARKET_CLOSED", True)
    allow_paper_when_closed: bool = _b("ALLOW_PAPER_WHEN_CLOSED", True)
    bist_paper_auto_follow: bool = _b("BIST_PAPER_AUTO_FOLLOW", False)
    paper_wallet_cycle_sec: int = _i("PAPER_WALLET_CYCLE_SEC", 90)
    # Auth
    auth_enabled: bool = _b("AUTH_ENABLED", False)
    auth_session_ttl_sec: int = _i("AUTH_SESSION_TTL_SEC", 86400)

    @property
    def is_live(self) -> bool:
        return self.mode == "LIVE"

    @property
    def is_production(self) -> bool:
        from data.validation import normalize_app_env, AppEnvironment

        return normalize_app_env(self.app_env) == AppEnvironment.PRODUCTION

    @property
    def normalized_app_env(self) -> str:
        from data.validation import normalize_app_env

        return normalize_app_env(self.app_env).value


settings = Settings()

SYSTEM_OBJECTIVES = (
    "SCAN AGGRESSIVELY · ANALYZE DEEPLY · FILTER AGGRESSIVELY · TRADE SELECTIVELY · "
    "MANAGE RISK STRICTLY · LET WINNERS RUN · CUT LOSSES QUICKLY. "
    "Capital first, positive expectancy second. No profit guarantee. LIVE default OFF. "
    "PRODUCTION: mock/simulated market data HARD BLOCKED."
)
