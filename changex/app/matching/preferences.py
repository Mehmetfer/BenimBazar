"""User matching preferences (chain opt-in / direct-only)."""

from __future__ import annotations

import time
from typing import Any

from .. import db
from ..domain_status import TradePreference


def get_user_preferences(conn, user_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM matching_preferences WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row:
        return {
            "user_id": user_id,
            "chain_opt_in": False,
            "trade_preference": TradePreference.DIRECT_ONLY.value,
            "max_chain_length": None,
            "updated_at": None,
        }
    return {
        "user_id": user_id,
        "chain_opt_in": bool(int(row["chain_opt_in"] or 0)),
        "trade_preference": row["trade_preference"] or TradePreference.DIRECT_ONLY.value,
        "max_chain_length": row["max_chain_length"],
        "updated_at": row["updated_at"],
    }


def set_user_preferences(
    conn,
    user_id: int,
    *,
    chain_opt_in: bool | None = None,
    trade_preference: str | None = None,
    max_chain_length: int | None = None,
) -> dict[str, Any]:
    current = get_user_preferences(conn, user_id)
    opt = current["chain_opt_in"] if chain_opt_in is None else bool(chain_opt_in)
    pref = current["trade_preference"] if trade_preference is None else trade_preference
    pref = str(pref).upper()
    if pref not in {TradePreference.DIRECT_ONLY.value, TradePreference.CHAIN_ALLOWED.value}:
        raise ValueError("invalid trade_preference")
    # max_chain_length stored for future; Exchange Graph V1 does not enforce chains
    mcl = current["max_chain_length"] if max_chain_length is None else max_chain_length
    if mcl is not None:
        mcl = int(mcl)
        if mcl < 2 or mcl > 10:
            raise ValueError("max_chain_length 2..10")
    now = time.time()
    conn.execute(
        """
        INSERT INTO matching_preferences(user_id, chain_opt_in, trade_preference, max_chain_length, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          chain_opt_in=excluded.chain_opt_in,
          trade_preference=excluded.trade_preference,
          max_chain_length=excluded.max_chain_length,
          updated_at=excluded.updated_at
        """,
        (user_id, 1 if opt else 0, pref, mcl, now),
    )
    return get_user_preferences(conn, user_id)


def public_preferences_view(prefs: dict[str, Any]) -> dict[str, Any]:
    """Strip any accidental PII — preferences API must stay privacy-safe."""
    return {
        "chain_opt_in": bool(prefs.get("chain_opt_in")),
        "trade_preference": prefs.get("trade_preference"),
        "max_chain_length": prefs.get("max_chain_length"),
        "updated_at": prefs.get("updated_at"),
        # Never expose email/phone/address here
    }
