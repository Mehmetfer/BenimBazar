"""Trading session modes — PRE_MARKET / INTRADAY / POST_MARKET."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from desk.models import DeskSessionMode

# BIST hours (Europe/Istanbul) — approximate
_BIST_OPEN = time(10, 0)
_BIST_CLOSE = time(18, 0)
_TZ = ZoneInfo("Europe/Istanbul")


def current_session_mode(*, now: datetime | None = None) -> DeskSessionMode:
    """Classify operational focus for the trading day."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(_TZ)
    t = local.time()
    wd = local.weekday()
    if wd >= 5:
        return DeskSessionMode.POST_MARKET
    if t < _BIST_OPEN:
        return DeskSessionMode.PRE_MARKET
    if t >= _BIST_CLOSE:
        return DeskSessionMode.POST_MARKET
    return DeskSessionMode.INTRADAY
