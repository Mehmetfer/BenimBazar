# FAVORITES.md — Watchlist & Priority Engine

**Core rule:** `FAVORITE ≠ BUY` · `FAVORITE = PRIORITY ANALYSIS`

## What favorites do
- Appear first in scan queue and dashboard
- Get deeper MTF / fund / news / sector pass
- Higher alert priority when signals fire
- User notes, groups, strategy preference, price alerts

## What favorites do NOT do
- Do not auto-upgrade NO_TRADE → BUY
- Are not the portfolio
- Do not bypass Risk Engine

## APIs
- `GET /api/favorites?sort=PRIORITY`
- `POST /api/favorites/{SYMBOL}/toggle`
- `PUT /api/favorites/{SYMBOL}` (notes, priority, strategy, groups)
- `GET /api/favorites/{SYMBOL}` detail + timeline
- `GET /api/favorites/scanner`
- `POST /api/favorites/price-alert`
- `GET /api/favorites/performance`

## UX order
1. Favorilerim  
2. Bugünün fırsatları  
3. Portföyüm  
4. Tüm piyasa  
