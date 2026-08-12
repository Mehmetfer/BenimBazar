"""Live-money readiness checklist — infrastructure for a future unlock.

This module NEVER enables live trading. It only reports what is missing.
Default outcome: NOT_READY / NOT VERIFIED.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from config.settings import settings
from execution.live_factory import live_adapter_status, resolve_live_adapter
from execution.broker_adapter import LiveBrokerDisabled

CheckStatus = Literal["PASS", "FAIL", "BLOCKED", "N/A"]


@dataclass
class ReadinessCheck:
    id: str
    title: str
    status: CheckStatus
    required_for_unlock: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LiveMoneyReadiness:
    ready: bool
    verdict: str  # NOT_READY | FOUNDATION_ONLY | READY_PENDING_HUMAN (never auto READY)
    live_money_readiness: str  # always "NOT VERIFIED" until separate human acceptance
    checks: list[ReadinessCheck] = field(default_factory=list)
    unlock_recipe: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "verdict": self.verdict,
            "live_money_readiness": self.live_money_readiness,
            "checks": [c.to_dict() for c in self.checks],
            "unlock_recipe": self.unlock_recipe,
            "warnings": self.warnings,
            "principle": "SIGNAL ≠ ORDER ≠ LIVE FILL — foundation does not unlock money",
        }


def evaluate_live_money_readiness(
    *,
    market_data_ok: bool | None = None,
    auth_ok: bool | None = None,
    reconcile_ok: bool | None = None,
    restart_recovery_ok: bool | None = None,
) -> LiveMoneyReadiness:
    """Evaluate checklist. Never returns ready=True while adapter is disabled."""
    checks: list[ReadinessCheck] = []
    warnings: list[str] = []

    from trading_safety.live_gate import is_live_broker_enabled, is_live_confirmed

    mode = str(getattr(settings, "mode", "PAPER")).upper()
    exec_mode = str(getattr(settings, "execution_mode", "PAPER")).upper()
    enabled = is_live_broker_enabled()
    confirmed = is_live_confirmed()
    confirm_req = bool(getattr(settings, "live_confirmation_required", True))
    kill = bool(getattr(settings, "kill_switch", False))
    auth_enabled = bool(getattr(settings, "auth_enabled", False))
    dry_run = bool(getattr(settings, "live_dry_run", True))
    adapter_id = str(getattr(settings, "live_broker_adapter", "") or "disabled")
    app_env = str(getattr(settings, "app_env", "DEVELOPMENT")).upper()

    adapter = resolve_live_adapter()
    adapter_meta = live_adapter_status()
    real_adapter = bool(adapter_meta.get("real_adapter_loaded"))

    def add(cid: str, title: str, ok: bool, required: bool, detail: str, blocked: bool = False) -> None:
        if blocked:
            st: CheckStatus = "BLOCKED"
        elif ok:
            st = "PASS"
        else:
            st = "FAIL"
        checks.append(ReadinessCheck(cid, title, st, required, detail))

    add(
        "live_broker_flag",
        "LIVE_BROKER_ENABLED",
        enabled,
        True,
        "true" if enabled else "false (default — locked)",
    )
    add(
        "live_confirmed",
        "LIVE_CONFIRMED (human)",
        (confirmed if confirm_req else True),
        True,
        f"confirmed={confirmed} required={confirm_req}",
    )
    add(
        "adapter_configured",
        "LIVE_BROKER_ADAPTER venue",
        real_adapter,
        True,
        f"id={adapter_id!r} name={adapter_meta.get('adapter_name')}",
        blocked=not real_adapter,
    )
    add(
        "not_kill_switch",
        "Kill switch off",
        not kill,
        True,
        "KILL_SWITCH active" if kill else "ok",
    )
    add(
        "auth_enabled",
        "AUTH_ENABLED for LIVE ops",
        auth_enabled if auth_ok is None else bool(auth_ok and auth_enabled),
        True,
        "AUTH_ENABLED=true required before live unlock" if not auth_enabled else "ok",
    )
    add(
        "dry_run_default",
        "LIVE_DRY_RUN safety net",
        dry_run or not enabled,
        False,
        f"LIVE_DRY_RUN={dry_run} (keep true until first micro-live acceptance)",
    )
    add(
        "execution_mode",
        "EXECUTION_MODE awareness",
        exec_mode in {"PAPER", "SHADOW", "MICRO_LIVE", "LIVE"},
        False,
        f"MODE={mode} EXECUTION_MODE={exec_mode}",
    )
    add(
        "app_env",
        "APP_ENV noted",
        True,
        False,
        f"APP_ENV={app_env} — PRODUCTION needs real MD + auth + adapter",
    )

    if market_data_ok is not None:
        add("market_data", "Live market data ready", bool(market_data_ok), True, "provider.has_market_data")
    else:
        checks.append(
            ReadinessCheck(
                "market_data",
                "Live market data ready",
                "N/A",
                True,
                "Not evaluated in this call — pass market_data_ok= from health",
            )
        )

    if reconcile_ok is not None:
        add("reconcile", "Bot↔broker reconcile OK", bool(reconcile_ok), True, "reconcile gate")
    else:
        checks.append(ReadinessCheck("reconcile", "Bot↔broker reconcile OK", "N/A", True, "Not evaluated"))

    if restart_recovery_ok is not None:
        add("restart", "Restart recovery OK", bool(restart_recovery_ok), True, "restart protocol")
    else:
        checks.append(ReadinessCheck("restart", "Restart recovery OK", "N/A", True, "Not evaluated"))

    # Hard rule: disabled adapter ⇒ never ready
    required_fail = [
        c
        for c in checks
        if c.required_for_unlock and c.status in {"FAIL", "BLOCKED"}
    ]
    ready = False  # foundation never auto-flips ready while adapter disabled
    if real_adapter and enabled and (confirmed or not confirm_req) and not kill and auth_enabled and not required_fail:
        # Still NOT claiming live money verified — human acceptance separate
        verdict = "READY_PENDING_HUMAN"
        warnings.append("Adapter flags green — live money still NOT VERIFIED until human acceptance + MICRO_LIVE trial")
    elif isinstance(adapter, LiveBrokerDisabled) or not real_adapter:
        verdict = "FOUNDATION_ONLY"
        warnings.append("No real venue adapter loaded — orders cannot reach a broker")
    else:
        verdict = "NOT_READY"

    recipe = [
        "1) Implement a real BrokerAdapter under execution/ (venue-specific)",
        "2) Register it in execution/live_factory.py resolve_live_adapter()",
        "3) Set LIVE_BROKER_ADAPTER=<id>",
        "4) Set AUTH_ENABLED=true (+ admin tokens)",
        "5) Verify market data + reconcile + restart recovery",
        "6) Set LIVE_BROKER_ENABLED=true and restart process",
        "7) Admin POST /api/live/confirm with phrase I_UNDERSTAND_LIVE_RISK",
        "8) Persist LIVE_CONFIRMED=true in env and restart",
        "9) Start MICRO_LIVE with hard caps; keep LIVE_DRY_RUN=true first",
        "10) Separate human acceptance before claiming live_money_readiness=VERIFIED",
    ]

    return LiveMoneyReadiness(
        ready=ready,
        verdict=verdict,
        live_money_readiness="NOT VERIFIED",
        checks=checks,
        unlock_recipe=recipe,
        warnings=warnings,
    )
