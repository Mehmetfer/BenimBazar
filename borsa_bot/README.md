# Borsa Bot

Sermaye koruma öncelikli BIST AL-SAT-BEKLE paper trading MVP.

Öncelik: kâr tahmini değil, sermaye korunması ve kontrollü risk.

## Çalıştır

```bash
cd /workspace
cp borsa_bot/.env.example borsa_bot/.env
source .venv/bin/activate
export PYTHONPATH=/workspace/borsa_bot
uvicorn dashboard.app:app --app-dir borsa_bot --host 0.0.0.0 --port 8090
```

Cep / masaüstü: http://127.0.0.1:8090

## Test

```bash
PYTHONPATH=/workspace/borsa_bot pytest borsa_bot/tests -q
```

## Mimari

| Modül | Görev |
|-------|--------|
| `data/` | Değiştirilebilir veri sağlayıcı (şimdilik simulated) |
| `indicators/` | EMA/RSI/MACD/BB/ATR/ADX/Stoch/VWAP/hacim/momentum |
| `strategy/` | Rejim + BUY/SELL skor + ensemble (Trend/EMA/Momentum/MR/Breakout) |
| `ai/` | Sinyal kalitesi / confidence — nihai emir vermez |
| `risk/` | ATR stop/TP, pozisyon/sektör/günlük zarar, LIVE preflight |
| `execution/` | Paper broker, duplicate koruması, kill switch / safety gate |
| `backtest/` | Net return, CAGR, Sharpe, Sortino, MDD, win rate, PF, B&H, look-ahead guard |
| `portfolio/` | SQLite paper ledger + decision log |
| `dashboard/` | Mobil API UI: portföy, AL/SAT/BEKLE, decision explanation |

## Güvenlik

- `MODE=PAPER` varsayılan
- `KILL_SWITCH=true` tüm girişleri keser
- LIVE broker emri bilerek kapalı; preflight geçmeden LIVE emir yok
- API anahtarları `.env` içinde (koda gömülmez)

## Sonraki aşamalar

1. Gerçek BIST/KAP veri adaptörleri
2. Walk-forward / OOS backtest genişletmesi
3. Paper trading doğrulama süresi
4. En son: broker entegrasyonu
