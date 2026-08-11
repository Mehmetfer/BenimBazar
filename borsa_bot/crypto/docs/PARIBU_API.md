# Paribu API — research notes (official docs.paribu.com)

Source of truth: https://docs.paribu.com/api (verified 2026-08-11).
Live probes against `https://api.paribu.com` confirm public REST paths **without** the `/api` prefix used in some rate-limit table rows.

## Base URL

`https://api.paribu.com`

## Market data (REST) — public, no API key

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /market/ticker` | None | All markets or `?market=btc_tl`. 24h snapshot. **No timestamp field.** Discovery source (~265 markets observed). |
| `GET /orderbook?market=` | None | Best bid/ask. `timestamp` unix seconds. Optional `depth` (max 20). |
| `GET /trades?market=&limit=` | None | Recent public trades. **`limit` must not exceed 20** (HTTP 400 / code 4001). |
| `GET /trades/history` | API key | Private — not used for public MD. |

## OHLCV / candles

**No official candlestick / kline / chart endpoint** (docs index has none; live probes of `/candles`, `/ohlcv`, `/kline`, `/chart` → 404).

OHLCV is derived by aggregating public trades (`/trades` + WebSocket `matches`) into canonical bars and persisting them (`database/crypto_trades.db`).  
Deep 240×15m history **cannot** be backfilled in one REST call — it accumulates over time. Until then: `INSUFFICIENT_HISTORY` → no BUY/STRONG_BUY autonomous trade.

## WebSocket (public)

- URL: `wss://api.paribu.com/v1/wapi/stream` (no auth)
- Subscribe: `{"method":"subscribe","channels":["orderbook:btc_tl","match-price:btc_tl","matches:btc_tl"],"id":"..."}`
- Server ping ~20s; pong within 30s or close `4002`
- Reconnect + resubscribe on any disconnect; orderbook gap → close `4003` → resubscribe

## Symbol format

Provider wire format: **lowercase** `base_quote`, e.g. `btc_tl`, `eth_usdt`.  
TRY is not used on the wire — quote is `tl`.

Application symbols: `BTC_TL` / display `BTC/TL`.  
Always keep `canonical_symbol` + `provider_symbol` separate.

## Rate limits (docs)

- GET weight bucket: 100,000 / minute
- Ticker weight 1; orderbook weight 2 (docs table may show `/api/...` paths; live public paths omit `/api`)
- HTTP 429 + `Retry-After` / `retry_after` when exceeded

## Authentication

Public market data and public WS: **no API key**.  
Private trading/account: HMAC — **out of scope** (no live crypto orders this phase).

## Bid / Ask policy

Ticker has **last** but not bid/ask. Bid/ask come from `/orderbook` or WS `orderbook`.  
**Never** set `bid = last` / `ask = last`. Unknown → bid/ask unset (0) + `UNKNOWN_SPREAD` blocks auto entry.

## Also observed (non-docs)

`https://www.paribu.com/ticker` — legacy public JSON. **Not used** — official `api.paribu.com` only.

## Capability matrix

| Capability | Status |
|------------|--------|
| Market discovery | PASS via `/market/ticker` |
| Live last price | PASS |
| Bid/ask | PASS via orderbook/WS only |
| OHLCV REST candles | NOT AVAILABLE |
| OHLCV from trades | PARTIAL (accumulates) |
| Public WS | AVAILABLE |
| Private orders | DISABLED this phase |
| Mock fallback | FORBIDDEN |
