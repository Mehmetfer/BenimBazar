# Live Money Foundation (gelecekte açılacak)

Bu katman **altyapıdır**. Gerçek para emri göndermez.

## İlkeler

- `LIVE_BROKER_ENABLED=false` (varsayılan)
- `LIVE_CONFIRMED=false` (varsayılan)
- `LIVE_BROKER_ADAPTER=disabled` (varsayılan)
- `LIVE_DRY_RUN=true` (varsayılan)
- Autonomy / self-improvement / agentic SE bu bayrakları **asla** açamaz
- `live_money_readiness` → **NOT VERIFIED** (otomatik flip yok)

## Bileşenler

| Dosya | Rol |
|-------|-----|
| `execution/broker_adapter.py` | `BrokerAdapter` Protocol + `LiveBrokerDisabled` + `ExecutionRouter` |
| `execution/live_factory.py` | Adapter seçimi (bilinmeyen → disabled) |
| `trading_safety/live_readiness.py` | Açılış kontrol listesi |
| `trading_safety/pipeline.py` | PAPER / SHADOW / MICRO_LIVE / LIVE fail-closed |
| `GET /api/live/readiness` | Checklist JSON |
| `POST /api/live/confirm` | İnsan teyidi (tek başına broker açmaz) |

## İleride açma sırası (manuel)

1. Gerçek `BrokerAdapter` yaz (matriks / info / custom HTTP…)
2. `live_factory.resolve_live_adapter()` içine kaydet
3. `AUTH_ENABLED=true`
4. Canlı market data + reconcile + restart recovery doğrula
5. `LIVE_BROKER_ADAPTER=<id>` + `LIVE_BROKER_ENABLED=true` → restart
6. Admin: `POST /api/live/confirm` phrase=`I_UNDERSTAND_LIVE_RISK`
7. `LIVE_CONFIRMED=true` → restart
8. Önce `MICRO_LIVE` + `LIVE_DRY_RUN=true`
9. Ayrı insan kabulü olmadan `live_money_readiness=VERIFIED` iddia etme

## API

```bash
curl -s http://127.0.0.1:8090/api/live/readiness | jq
curl -s http://127.0.0.1:8090/api/live/status | jq
```

`ready` her zaman foundation aşamasında `false` kalır; gerçek adapter + insan kapısı olmadan açılmaz.
