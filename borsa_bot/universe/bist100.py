"""BIST 100 universe loader and filterable listing service.

Primary focus of the product: XU100 constituents from bist100_companies.json.
Does not invent live prices — listing metadata only; charts via TradingView.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "bist100_companies.json"


@dataclass(frozen=True)
class Bist100Company:
    ticker: str
    name: str
    sector: str

    @property
    def tradingview_symbol(self) -> str:
        return f"BIST:{self.ticker}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tradingview_symbol"] = self.tradingview_symbol
        d["exchange"] = "BIST"
        d["index"] = "XU100"
        return d


def _fold(text: str) -> str:
    """Case/diacritic-insensitive match for TR search."""
    norm = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).casefold()


@lru_cache(maxsize=1)
def load_bist100_dataset() -> dict[str, Any]:
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"BIST 100 dataset missing: {DATA_FILE}")
    with DATA_FILE.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    companies = raw.get("companies") or []
    if len(companies) != 100:
        raise ValueError(f"BIST 100 dataset must contain 100 companies, got {len(companies)}")
    for row in companies:
        for key in ("ticker", "name", "sector"):
            if not str(row.get(key) or "").strip():
                raise ValueError(f"Invalid company row missing {key}: {row!r}")
    return raw


def list_companies() -> list[Bist100Company]:
    data = load_bist100_dataset()
    out: list[Bist100Company] = []
    for row in data["companies"]:
        out.append(
            Bist100Company(
                ticker=str(row["ticker"]).strip().upper(),
                name=str(row["name"]).strip(),
                sector=str(row["sector"]).strip(),
            )
        )
    return sorted(out, key=lambda c: c.ticker)


def get_company(ticker: str) -> Bist100Company | None:
    key = (ticker or "").strip().upper()
    for c in list_companies():
        if c.ticker == key:
            return c
    return None


def list_sectors() -> list[str]:
    return sorted({c.sector for c in list_companies()})


def filter_companies(
    *,
    q: str | None = None,
    sector: str | None = None,
    ticker: str | None = None,
) -> list[Bist100Company]:
    rows = list_companies()
    if ticker:
        t = ticker.strip().upper()
        rows = [c for c in rows if c.ticker == t]
    if sector:
        s = _fold(sector.strip())
        rows = [c for c in rows if _fold(c.sector) == s]
    if q:
        needle = _fold(q.strip())
        if needle:
            rows = [
                c
                for c in rows
                if needle in _fold(c.ticker) or needle in _fold(c.name) or needle in _fold(c.sector)
            ]
    return rows


def catalog_payload(
    *,
    q: str | None = None,
    sector: str | None = None,
    ticker: str | None = None,
) -> dict[str, Any]:
    meta = load_bist100_dataset()
    items = filter_companies(q=q, sector=sector, ticker=ticker)
    return {
        "index": meta.get("index", "XU100"),
        "index_name": meta.get("index_name", "BIST 100"),
        "exchange": meta.get("exchange", "BIST"),
        "currency": meta.get("currency", "TRY"),
        "tradingview_prefix": meta.get("tradingview_prefix", "BIST"),
        "updated": meta.get("updated"),
        "source_note": meta.get("source_note"),
        "count": len(items),
        "total": 100,
        "sectors": list_sectors(),
        "companies": [c.to_dict() for c in items],
        "principle": "BIST 100 listing metadata — prices/charts via TradingView; SIGNAL ≠ ORDER",
    }
