from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Protocol

from config.models import Bar, QuoteSnapshot


UNIVERSE: dict[str, tuple[str, str, float]] = {
    "THYAO": ("Türk Hava Yolları", "ULASTIRMA", 312.5),
    "ASELS": ("Aselsan", "SAVUNMA", 78.4),
    "GARAN": ("Garanti BBVA", "BANKA", 118.2),
    "EREGL": ("Erdemir", "METAL", 54.75),
    "BIMAS": ("BİM", "PERAKENDE", 542.0),
    "AKBNK": ("Akbank", "BANKA", 64.3),
    "SAHOL": ("Sabancı Holding", "HOLDING", 98.1),
    "KCHOL": ("Koç Holding", "HOLDING", 186.4),
    "TUPRS": ("Tüpraş", "ENERJI", 168.9),
    "SISE": ("Şişecam", "SANAYI", 49.85),
    "XU100": ("BIST 100", "ENDEX", 10000.0),
}


class MarketDataProvider(Protocol):
    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]: ...
    def get_quote(self, symbol: str) -> QuoteSnapshot: ...
    def list_symbols(self) -> list[str]: ...
    def tick(self) -> None: ...
    def is_fresh(self, max_age_sec: float = 30.0) -> bool: ...


class SimulatedProvider:
    """Deterministic-ish OHLCV simulator for paper trading MVP."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._bars: dict[str, list[Bar]] = {}
        self._last_tick = datetime.now(timezone.utc)
        self._init_history()

    def _init_history(self) -> None:
        now = datetime.now(timezone.utc)
        for symbol, (_, _, base) in UNIVERSE.items():
            bars: list[Bar] = []
            price = base * (0.9 + self._rng.random() * 0.1)
            for i in range(240):
                drift = (self._rng.random() - 0.48) * (0.012 if symbol != "XU100" else 0.006)
                o = price
                c = max(0.5, o * (1 + drift))
                h = max(o, c) * (1 + self._rng.random() * 0.006)
                l = min(o, c) * (1 - self._rng.random() * 0.006)
                vol = 1_000_000 * (0.5 + self._rng.random())
                trades = int(800 + self._rng.random() * 2200)
                bars.append(
                    Bar(
                        ts=now - timedelta(minutes=15 * (240 - i)),
                        open=round(o, 2),
                        high=round(h, 2),
                        low=round(l, 2),
                        close=round(c, 2),
                        volume=round(vol, 0),
                        trades=trades,
                    )
                )
                price = c
            self._bars[symbol] = bars

    def tick(self) -> None:
        now = datetime.now(timezone.utc)
        for symbol, bars in self._bars.items():
            last = bars[-1]
            scale = 0.01 if symbol != "XU100" else 0.004
            drift = (self._rng.random() - 0.5) * scale
            o = last.close
            c = max(0.5, o * (1 + drift))
            h = max(o, c) * (1 + self._rng.random() * 0.004)
            l = min(o, c) * (1 - self._rng.random() * 0.004)
            vol = last.volume * (0.8 + self._rng.random() * 0.5)
            bars.append(
                Bar(
                    ts=now,
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=round(vol, 0),
                    trades=int(700 + self._rng.random() * 2500),
                )
            )
            if len(bars) > 300:
                del bars[0 : len(bars) - 300]
        self._last_tick = now

    def get_bars(self, symbol: str, lookback: int = 220) -> list[Bar]:
        return list(self._bars[symbol][-lookback:])

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        name, sector, _ = UNIVERSE[symbol]
        bar = self._bars[symbol][-1]
        spread = max(0.01, bar.close * 0.0008)
        return QuoteSnapshot(
            symbol=symbol,
            name=name,
            sector=sector,
            price=bar.close,
            bid=round(bar.close - spread / 2, 2),
            ask=round(bar.close + spread / 2, 2),
            volume=bar.volume,
            trades=bar.trades,
            ts=bar.ts,
        )

    def list_symbols(self) -> list[str]:
        return [s for s in UNIVERSE if s != "XU100"]

    def is_fresh(self, max_age_sec: float = 30.0) -> bool:
        age = (datetime.now(timezone.utc) - self._last_tick).total_seconds()
        return age <= max_age_sec


def create_provider(name: str = "simulated") -> MarketDataProvider:
    if name == "simulated":
        return SimulatedProvider()
    # Future: yahoo/kap/broker adapters plug in here.
    raise ValueError(f"Unknown data provider: {name}")
