from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass
class Quote:
    symbol: str
    name: str
    price: float
    change_pct: float


# Simulated BIST-like paper market
_SEED: dict[str, tuple[str, float]] = {
    "THYAO": ("Türk Hava Yolları", 312.50),
    "ASELS": ("Aselsan", 78.40),
    "GARAN": ("Garanti BBVA", 118.20),
    "EREGL": ("Erdemir", 54.75),
    "BIMAS": ("BİM", 542.00),
    "AKBNK": ("Akbank", 64.30),
    "SAHOL": ("Sabancı Holding", 98.10),
    "KCHOL": ("Koç Holding", 186.40),
    "TUPRS": ("Tüpraş", 168.90),
    "SISE": ("Şişecam", 49.85),
}

_state: dict[str, float] = {k: v[1] for k, v in _SEED.items()}
_last_tick = 0.0


def _tick() -> None:
    global _last_tick
    now = time.time()
    if now - _last_tick < 2.0:
        return
    _last_tick = now
    rng = random.Random(int(now) // 2)
    for symbol, base in list(_state.items()):
        seed_price = _SEED[symbol][1]
        drift = rng.uniform(-0.012, 0.012)
        nxt = max(seed_price * 0.7, min(seed_price * 1.4, base * (1 + drift)))
        _state[symbol] = round(nxt, 2)


def list_quotes() -> list[Quote]:
    _tick()
    quotes: list[Quote] = []
    for symbol, (name, seed) in _SEED.items():
        price = _state[symbol]
        change = ((price - seed) / seed) * 100
        quotes.append(Quote(symbol, name, price, round(change, 2)))
    quotes.sort(key=lambda q: q.symbol)
    return quotes


def get_price(symbol: str) -> float | None:
    _tick()
    key = (symbol or "").strip().upper()
    return _state.get(key)


def get_quote(symbol: str) -> Quote | None:
    key = (symbol or "").strip().upper()
    if key not in _SEED:
        return None
    price = get_price(key)
    if price is None:
        return None
    name, seed = _SEED[key]
    return Quote(key, name, price, round(((price - seed) / seed) * 100, 2))
