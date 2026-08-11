"""Tradeable BIST universe catalog — separate from XU100 index membership.

FULL MARKET UNIVERSE (catalog) ≠ prices. Live discovery may refine when provider connected.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_DIR = Path(__file__).resolve().parents[1] / "data" / "catalog"
UNIVERSE_FILE = CATALOG_DIR / "bist_universe.json"
BIST100_CATALOG = CATALOG_DIR / "bist100.json"


@dataclass(frozen=True)
class TradeableInstrument:
    symbol: str
    name: str
    exchange: str = "BIST"
    market: str = "BIST"
    sector: str = ""
    currency: str = "TRY"
    status: str = "ACTIVE"
    tradable: bool = True
    lot_size: int = 1
    tick_size: float | None = None
    xu100: bool = False
    index_membership: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["index_membership"] = list(self.index_membership)
        return d


@lru_cache(maxsize=1)
def load_tradeable_universe() -> dict[str, Any]:
    if not UNIVERSE_FILE.is_file():
        raise FileNotFoundError(f"Tradeable universe missing: {UNIVERSE_FILE}")
    with UNIVERSE_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def list_tradeable(*, active_only: bool = True, tradable_only: bool = True) -> list[TradeableInstrument]:
    raw = load_tradeable_universe()
    out: list[TradeableInstrument] = []
    for row in raw.get("instruments") or []:
        status = str(row.get("status") or "ACTIVE").upper()
        tradable = bool(row.get("tradable", True))
        if active_only and status not in {"ACTIVE", "TRADEABLE"}:
            continue
        if tradable_only and not tradable:
            continue
        out.append(
            TradeableInstrument(
                symbol=str(row["symbol"]).strip().upper(),
                name=str(row.get("name") or ""),
                exchange=str(row.get("exchange") or "BIST"),
                market=str(row.get("market") or "BIST"),
                sector=str(row.get("sector") or ""),
                currency=str(row.get("currency") or "TRY"),
                status=status,
                tradable=tradable,
                lot_size=int(row.get("lot_size") or 1),
                tick_size=row.get("tick_size"),
                xu100=bool(row.get("xu100")),
                index_membership=tuple(row.get("index_membership") or []),
            )
        )
    return sorted(out, key=lambda x: x.symbol)


def list_tradeable_symbols() -> list[str]:
    return [i.symbol for i in list_tradeable()]


def universe_stats() -> dict[str, Any]:
    items = list_tradeable(active_only=False, tradable_only=False)
    active = [i for i in items if i.status == "ACTIVE" and i.tradable]
    return {
        "full_universe": len(items),
        "active_tradeable": len(active),
        "xu100_members": sum(1 for i in items if i.xu100),
        "catalog_file": str(UNIVERSE_FILE.name),
        "note": "Catalog metadata only — not live quotes. Analyzer count comes from provider MD intersection.",
    }
