# Borsa Bot

İki temel hedef:

1. **Sermaye koruma**
2. **Risk-ayarlı kâr üretme**

Öncelik sırası: Sermaye koruma → risk kontrolü → kayıp kontrolü → yüksek olasılıklı fırsatlar → R/R optimizasyonu → kâr maksimizasyonu.

Amaç: *Minimum gereksiz risk ile maksimum sürdürülebilir risk-ayarlı getiri.*  
Aşırı pasif değil; agresif getiri botu da değil. **NO_TRADE / WAIT** birinci sınıf çıktıdır.

Kâr garantisi yoktur. Geçmiş performans geleceği garanti etmez. LIVE öncesi paper trading zorunludur.

## Yeni karar katmanları

- **Expected Value:** negatif EV otomatik red; pozitif EV tek başına yetmez
- **Dinamik sizing:** confidence × vol × stop × regime × capital mode
- **Partial TP:** T1/T2/T3 %25 + trailing kalan (config)
- **Profit protection:** breakeven → ATR/EMA trailing; stop asla genişlemez
- **No DCA default:** kaybeden pozisyona ekleme yok
- **Capital modes:** NORMAL → DEFENSIVE → HIGH_RISK → CAPITAL_PROTECTION → KILL_SWITCH
- **Risk-adjusted strategy ranking:** yüksek getiri + yüksek DD cezalı
- **Alerts:** uygulama içi + push/SMS stub + ses + TTS (TR); SIGNAL ≠ EXECUTION; trading’i etkilemez

## Çalıştır

```bash
cd /workspace
cp borsa_bot/.env.example borsa_bot/.env
source .venv/bin/activate
# Uvicorn app-dir flat imports için hâlâ borsa_bot path ister:
export PYTHONPATH=/workspace/borsa_bot
uvicorn dashboard.app:app --app-dir borsa_bot --host 0.0.0.0 --port 8090
```

## Test

Kök `pytest.ini` `pythonpath = . borsa_bot` ayarlar; düz `pytest` collection hatası vermez:

```bash
cd /workspace
source .venv/bin/activate
pytest                 # tüm suite’ler (changex + companion + borsa_bot)
pytest borsa_bot/tests -q
```

## Modüller

| Klasör | Görev |
|--------|--------|
| `data/` | Modüler veri sağlayıcı (simulated MVP) |
| `indicators/` | EMA/SMA/RSI/MACD/ADX/ATR/BB/Stoch/StochRSI/VWAP/OBV/MFI/CMF/ROC… |
| `technical/` | Multi-timeframe + sektör relative strength |
| `fundamental/` | Kalite/büyüme/değerleme/risk skorları (stub veri) |
| `news/` | KAP/haber sınıflandırma stub (yoksa uydurmaz) |
| `market_regime/` | STRONG_BULL…STRONG_BEAR + breadth |
| `signals/` | Çok skorlu motor + çatışma filtresi + trade plan |
| `ai/` | Confidence / anomali / vol rejimi (emir vermez) |
| `risk/` | Risk-based sizing, R:R≥1.5, T1–T3, pause, kill switch |
| `execution/` | Paper broker + safety gate + duplicate koruma |
| `alerts/` | Event bus → manager → IN_APP/PUSH/SOUND/TTS/SMS (karar etkilemez) |
| `backtest/` | Komisyon/slippage + metrikler + look-ahead guard |
| `paper_trading/` | Paper facade |
| `dashboard/` | Mobil UI: skorlar, NEDEN/RİSKLER, manuel onaylı paper emir |

## Geliştirme aşamaları

PHASE 1–9: Data → Indicators → Regime → Signal → Risk → Backtest → AI → Dashboard → Paper  
PHASE 10: Broker (henüz yok, bilinçli olarak kapalı)

## Sonraki

Gerçek BIST/KAP adaptörleri → walk-forward OOS → uzun paper → manuel onaylı küçük canlı.
