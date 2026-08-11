"""AI dynamic watchlist — observation priority only; NEVER a risk bypass."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.models import utc_now
from config.settings import ROOT


@dataclass
class WatchItem:
    symbol: str
    market_type: str
    rank: int
    reason: str = "AI_SELECTED"
    added_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIWatchlist:
    """Dynamic watchlist separate from user FavoritesStore."""

    def __init__(self, path: Path | None = None, *, max_items: int = 15) -> None:
        self.path = path or (ROOT / "database" / "ai_watchlist.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self._lock = threading.Lock()
        if not self.path.exists():
            self._write({"items": [], "updated_at": utc_now().isoformat(), "note": "Watchlist ≠ trading permission"})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def list_items(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._read().get("items") or [])

    def rebuild_from_ranked(
        self,
        ranked: list[Any],
        *,
        market_type: str = "BIST",
    ) -> list[dict[str, Any]]:
        """Replace watchlist from opportunity ranks (ADD/REMOVE/REORDER)."""
        items: list[dict[str, Any]] = []
        for i, opp in enumerate(ranked[: self.max_items]):
            sym = getattr(opp, "symbol", None) or (opp.get("symbol") if isinstance(opp, dict) else None)
            if not sym:
                continue
            reason = "TOP_OPPORTUNITY" if i == 0 else ("ENTRY_CANDIDATE" if getattr(opp, "action", "") in {"BUY", "STRONG_BUY", "AL"} else "WATCH")
            items.append(
                WatchItem(
                    symbol=str(sym).upper(),
                    market_type=market_type,
                    rank=i + 1,
                    reason=reason,
                    added_at=utc_now().isoformat(),
                ).to_dict()
            )
        with self._lock:
            self._write(
                {
                    "items": items,
                    "updated_at": utc_now().isoformat(),
                    "note": "AI watchlist is priority for analysis only — Favorites ≠ risk bypass; Watchlist ≠ order",
                }
            )
        return items
