# Paribu API — Phase 2 research notes

Source of truth: official docs at https://docs.paribu.com/api (verified 2026-08-11).

## Base URL

`https://api.paribu.com`

## Market data (REST)

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /market/ticker` | None | All markets or `?market=btc_tl`. 24h snapshot. **No timestamp field.** |
| `GET /orderbook?market=` | None | Best bid/ask. `timestamp` unix seconds. Optional `depth` (max 20). |
| `GET /trades?market=&limit=` | None (verified) | Recent public trades. Small `limit` only (e.g. 5). |
| `GET /trades/history` | API key | Private — not used for public MD. |

## OHLCV / candles

**No official candlestick / kline / chart endpoint** in docs (`ask` confirmed).

OHLCV is derived by aggregating public trades (`/trades` + WebSocket `matches`) into canonical bars. Deep history requires accumulating trades over time; do not invent bars.

## WebSocket (public)

- URL: `wss://api.paribu.com/v1/wapi/stream` (no auth)
- Subscribe: `{"method":"subscribe","channels":["orderbook:btc_tl","match-price:btc_tl","matches:btc_tl"],"id":"..."}`
- Server ping ~20s; pong within 30s or close `4002`
- Reconnect + resubscribe on any disconnect; orderbook gap → close `4003` → resubscribe

## Symbol format

Provider wire format: **lowercase** `base_quote`, e.g. `btc_tl`, `eth_usdt`.  
TRY is not used on the wire — quote is `tl`.

Application symbols: `BTC_TL` / display `BTC/TL`.

## Rate limits (docs)

- GET weight bucket: 100,000 / minute
- `GET /market/ticker` weight 1; `GET /orderbook` weight 2
- HTTP 429 + `Retry-After` / `retry_after` when exceeded

## Authentication

Public market data and public WS: **no API key**.  
Private trading/account: HMAC — **out of scope** for Phase 2 (no orders).

## Also observed (non-docs)

`https://www.paribu.com/ticker` — legacy public JSON keyed `BTC_TL` with bid/ask. Phase 2 uses **official** `api.paribu.com` only.
