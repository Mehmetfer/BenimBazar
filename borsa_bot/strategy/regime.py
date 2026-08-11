from __future__ import annotations

"""Compatibility shim — prefer market_regime.engine."""

from market_regime.engine import detect_regime, regime_buy_threshold_boost, trend_label

__all__ = ["detect_regime", "trend_label", "regime_buy_threshold_boost"]
