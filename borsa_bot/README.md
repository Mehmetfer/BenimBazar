# Borsa Bot

Sermaye koruma öncelikli BIST **AL / SAT / BEKLE** paper trading sistemi.

## Felsefe

1. Önce sermayeyi koru  
2. Emin değilsen **BEKLE**  
3. Risk Engine sinyal motorundan üstündür  
4. AI karar verici değil, analiz yardımcısıdır  
5. Skor tek başına emir açtırmaz  
6. LIVE varsayılan kapalı; manuel onay açık  

Zarar etmeyen / kâr garantili sistem iddiası yoktur.

## Çalıştır

```bash
cd /workspace
cp borsa_bot/.env.example borsa_bot/.env
source .venv/bin/activate
export PYTHONPATH=/workspace/borsa_bot
uvicorn dashboard.app:app --app-dir borsa_bot --host 0.0.0.0 --port 8090
```

## Test

```bash
PYTHONPATH=/workspace/borsa_bot pytest borsa_bot/tests -q
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
| `backtest/` | Komisyon/slippage + metrikler + look-ahead guard |
| `paper_trading/` | Paper facade |
| `dashboard/` | Mobil UI: skorlar, NEDEN/RİSKLER, manuel onaylı paper emir |

## Geliştirme aşamaları

PHASE 1–9: Data → Indicators → Regime → Signal → Risk → Backtest → AI → Dashboard → Paper  
PHASE 10: Broker (henüz yok, bilinçli olarak kapalı)

## Sonraki

Gerçek BIST/KAP adaptörleri → walk-forward OOS → uzun paper → manuel onaylı küçük canlı.
