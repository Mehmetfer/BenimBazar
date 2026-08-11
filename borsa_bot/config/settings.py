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
    mode: str = os.getenv("MODE", "PAPER").upper()
    starting_cash: float = _f("STARTING_CASH", 100_000)
    max_portfolio_risk_pct: float = _f("MAX_PORTFOLIO_RISK_PCT", 1.0)
    max_position_risk_pct: float = _f("MAX_POSITION_RISK_PCT", 0.75)
    max_open_positions: int = _i("MAX_OPEN_POSITIONS", 5)
    max_sector_positions: int = _i("MAX_SECTOR_POSITIONS", 2)
    daily_max_loss_pct: float = _f("DAILY_MAX_LOSS_PCT", 2.0)
    atr_stop_mult: float = _f("ATR_STOP_MULT", 2.0)
    atr_take_mult: float = _f("ATR_TAKE_MULT", 3.0)
    buy_score_threshold: float = _f("BUY_SCORE_THRESHOLD", 75)
    sell_score_threshold: float = _f("SELL_SCORE_THRESHOLD", 75)
    commission_pct: float = _f("COMMISSION_PCT", 0.002)
    slippage_pct: float = _f("SLIPPAGE_PCT", 0.0005)
    data_provider: str = os.getenv("DATA_PROVIDER", "simulated")
    kill_switch: bool = _b("KILL_SWITCH", False)
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = _i("API_PORT", 8090)
    db_path: Path = ROOT / "database" / "paper.db"
    log_dir: Path = ROOT / "logs"

    @property
    def is_live(self) -> bool:
        return self.mode == "LIVE"


settings = Settings()
