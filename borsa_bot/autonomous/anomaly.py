"""Data anomaly engine — fail-closed helpers (Master V2 §8).

Does not invent prices. Critical anomalies → NO TRADE recommendation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from config.models import Bar, QuoteSnapshot


@dataclass
class AnomalyFinding:
    code: str
    severity: str  # INFO | WARNING | HIGH | CRITICAL
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnomalyReport:
    ok: bool
    trade_allowed: bool
    findings: list[AnomalyFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "trade_allowed": self.trade_allowed,
            "findings": [f.to_dict() for f in self.findings],
        }


def inspect_quote(quote: QuoteSnapshot, *, max_spread_pct: float = 2.0) -> AnomalyReport:
    findings: list[AnomalyFinding] = []
    if quote.price is None or quote.price <= 0:
        findings.append(AnomalyFinding("INVALID_PRICE", "CRITICAL", "price<=0"))
    if quote.bid is not None and quote.ask is not None:
        if quote.bid > quote.ask:
            findings.append(AnomalyFinding("BID_GT_ASK", "CRITICAL", f"bid={quote.bid} ask={quote.ask}"))
        if quote.bid < 0 or quote.ask < 0:
            findings.append(AnomalyFinding("NEGATIVE_QUOTE", "CRITICAL"))
    spread = float(getattr(quote, "spread_pct", 0) or 0)
    if spread > max_spread_pct:
        findings.append(AnomalyFinding("ABNORMAL_SPREAD", "HIGH", f"spread_pct={spread}"))
    if quote.volume is not None and quote.volume < 0:
        findings.append(AnomalyFinding("NEGATIVE_VOLUME", "CRITICAL"))
    kind = str(getattr(quote, "data_source_kind", "") or "").upper()
    if kind in {"UNKNOWN", "MOCK"}:
        findings.append(AnomalyFinding("BAD_PROVENANCE", "CRITICAL", kind))
    critical = any(f.severity == "CRITICAL" for f in findings)
    high = any(f.severity == "HIGH" for f in findings)
    return AnomalyReport(ok=not critical, trade_allowed=not critical and not high, findings=findings)


def inspect_bars(bars: Sequence[Bar], *, max_gap_mult: float = 4.0) -> AnomalyReport:
    findings: list[AnomalyFinding] = []
    if not bars:
        findings.append(AnomalyFinding("MISSING_BARS", "CRITICAL"))
        return AnomalyReport(False, False, findings)
    prev_ts = None
    prev_close = None
    gaps = []
    for b in bars:
        if b.close <= 0 or b.high < b.low or b.open <= 0:
            findings.append(AnomalyFinding("INVALID_OHLC", "CRITICAL", f"ts={b.ts}"))
            break
        if b.volume is not None and b.volume < 0:
            findings.append(AnomalyFinding("NEGATIVE_VOLUME", "CRITICAL"))
            break
        if prev_ts is not None:
            delta = (b.ts - prev_ts).total_seconds()
            if delta < 0:
                findings.append(AnomalyFinding("TIMESTAMP_REVERSAL", "CRITICAL"))
                break
            if delta == 0:
                findings.append(AnomalyFinding("DUPLICATE_BAR", "HIGH"))
            gaps.append(delta)
        if prev_close and prev_close > 0:
            chg = abs(b.close / prev_close - 1.0)
            if chg > 0.25:  # 25% single-bar — flag, do not invent correction
                findings.append(AnomalyFinding("PRICE_SPIKE", "HIGH", f"chg={chg:.2%}"))
        prev_ts = b.ts
        prev_close = b.close
    if gaps:
        # median-ish: use sorted mid
        sg = sorted(gaps)
        med = sg[len(sg) // 2]
        if med > 0:
            for g in gaps[-5:]:
                if g > med * max_gap_mult:
                    findings.append(AnomalyFinding("TIME_GAP", "WARNING", f"gap_sec={g}"))
                    break
    # zero volume streak
    zeros = sum(1 for b in bars[-20:] if (b.volume or 0) == 0)
    if zeros >= 15:
        findings.append(AnomalyFinding("ZERO_VOLUME", "WARNING", f"zeros={zeros}"))
    critical = any(f.severity == "CRITICAL" for f in findings)
    high = any(f.severity == "HIGH" for f in findings)
    return AnomalyReport(ok=not critical, trade_allowed=not critical and not high, findings=findings)


def inspect_symbol(quote: QuoteSnapshot, bars: Sequence[Bar], *, max_spread_pct: float = 2.0) -> AnomalyReport:
    q = inspect_quote(quote, max_spread_pct=max_spread_pct)
    b = inspect_bars(bars)
    findings = q.findings + b.findings
    critical = any(f.severity == "CRITICAL" for f in findings)
    high = any(f.severity == "HIGH" for f in findings)
    return AnomalyReport(ok=not critical, trade_allowed=not critical and not high, findings=findings)
