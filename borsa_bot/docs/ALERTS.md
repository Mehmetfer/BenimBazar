# ALERTS.md — Multi-channel Notification Engine

**Rule:** Alerts inform the user. They never place, modify, or cancel orders.  
**Rule:** `SIGNAL ≠ EXECUTION` — AI BUY is not ORDER_FILLED.

## Flow

```
AI / Risk / Execution produce domain events
        ↓
   EventBus.publish(TradingAlertEvent)
        ↓
   AlertManager (priority · cooldown · quiet hours · prefs)
        ↓
   Channel router: IN_APP · PUSH · SOUND · TTS · SMS
        ↓
   NotificationLog (+ in-app inbox)
```

## Priorities

| Priority | Examples |
|----------|----------|
| LOW | MARKET_UPDATE |
| NORMAL | WATCH, daily summary, order submitted |
| HIGH | BUY/SELL signal, TAKE_PROFIT, ORDER_FILLED |
| CRITICAL | STOP_LOSS, KILL_SWITCH, RISK_ALERT, ORDER_REJECTED |

## Channels

| Channel | Behavior (2026-honest) |
|---------|------------------------|
| IN_APP | SQLite inbox + dashboard |
| PUSH | No-op unless `PUSH_ENABLED` + key; HTTP adapter not claimed |
| SOUND | Server records profile; browser Web Audio plays |
| TTS | Turkish text; browser `speechSynthesis` (`tr-TR`) |
| SMS | `SmsProvider` abstraction (`null` / `log_only` / `http_stub`) |

## Config (`.env`)

- `SMS_ON`, `PUSH_ON`, `SOUND_ON`, `TTS_ON`
- `ALERT_COOLDOWN_SECONDS`
- `SMS_PROVIDER`, `SMS_API_URL`, `SMS_API_KEY`, `SMS_TO` (never log keys)
- `PUSH_ENABLED`, `PUSH_SERVER_KEY` / `FCM_SERVER_KEY`

## APIs

- `GET /api/notifications`
- `GET|PUT /api/notifications/settings`
- `POST /api/notifications/read`
- `POST /api/notifications/daily-summary`
- `POST /api/notifications/test?kind=BUY_SIGNAL&symbol=THYAO`
