"""Simple Live Trading Dashboard (§105)

## Design

LESS DATA, MORE DECISION — mobile-first daily trading home.

## Absolute integrity

- Fabricated prices must never be labeled **CANLI**.
- `SimulatedProvider` → `SİMÜLE FİYAT` / `FRESH_SIMULATED` / `live_ready=false`.
- Missing live credentials → `RequiredLiveProvider` → **VERİ YOK** / **DATA SOURCE REQUIRED**.
- Stale feed → **STALE DATA**, signals paused, no new STRONG BUY.
- News/KAP without real source → `UNAVAILABLE` (not invented headlines).
- AI confidence ≠ historical accuracy (separate labels).

## Main screen order

1. Market status (BIST open/closed + last update + source)
2. ★ Favorites opportunities
3. 🔥 Strong Buy
4. Buy
5. Wait
6. Sell

## APIs

- `GET /api/daily` — home payload
- `GET /api/symbol/{symbol}` — detail (plan, forecast, news/KAP honesty)
- `GET /api/dashboard` — includes `daily` + `data_source` + `live_ready`

## Config

- `DATA_PROVIDER=simulated|required|live`
- `MARKET_DATA_URL` + `MARKET_DATA_TOKEN` required for `live`
- `DATA_FRESHNESS_SEC`, `SIGNAL_TTL_SEC`, `DAILY_TOP_N`

## LIVE READY

Acceptance checklist must all pass before `live_ready=true`.
Until a verified live market feed + broker path exists, **LIVE READY = false**.
"""
