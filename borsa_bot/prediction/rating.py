from __future__ import annotations

import math
from collections import defaultdict

from config.settings import Settings, settings as default_settings
from prediction.models import ReliabilityGrade, ReliabilityReport, SampleTier


def sample_tier(n: int, cfg: Settings | None = None) -> SampleTier:
    cfg = cfg or default_settings
    if n < getattr(cfg, "pred_sample_insufficient", 50):
        return SampleTier.INSUFFICIENT
    if n < getattr(cfg, "pred_sample_provisional", 100):
        return SampleTier.PROVISIONAL
    if n < getattr(cfg, "pred_sample_validated", 500):
        return SampleTier.VALIDATED
    return SampleTier.HIGH_CONFIDENCE


def directional_accuracy(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return sum(1 for r in rows if r.get("direction_correct")) / len(rows)


def mae(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return sum(abs(float(r.get("return_error_pp") or 0)) for r in rows) / len(rows)


def rmse(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return math.sqrt(sum(float(r.get("return_error_pp") or 0) ** 2 for r in rows) / len(rows))


def mape_safe(rows: list[dict], eps: float = 1.0) -> float | None:
    """MAPE on returns with floor to avoid blow-up near zero prices/returns."""
    if not rows:
        return None
    vals = []
    for r in rows:
        actual = abs(float(r.get("actual_return_pct") or 0))
        err = abs(float(r.get("return_error_pp") or 0))
        vals.append(err / max(actual, eps))
    return sum(vals) / len(vals) * 100.0


def brier_score(rows: list[dict]) -> float | None:
    """Binary Brier on direction correctness vs stated probability."""
    if not rows:
        return None
    s = 0.0
    for r in rows:
        p = float(r.get("probability") or 0.5)
        o = 1.0 if r.get("direction_correct") else 0.0
        s += (p - o) ** 2
    return s / len(rows)


def calibration_buckets(rows: list[dict]) -> list[dict]:
    buckets = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
    out = []
    for lo, hi in buckets:
        subset = [r for r in rows if lo <= float(r.get("confidence") or 0) < hi]
        n = len(subset)
        hit = directional_accuracy(subset)
        mean_conf = (sum(float(r.get("confidence") or 0) for r in subset) / n) if n else None
        note = "INSUFFICIENT"
        if n >= 20 and hit is not None and mean_conf is not None:
            gap = mean_conf / 100.0 - hit
            if gap > 0.08:
                note = "OVERCONFIDENT"
            elif gap < -0.08:
                note = "UNDERCONFIDENT"
            else:
                note = "GOOD_CALIBRATION"
        out.append(
            {
                "range": f"{lo}-{hi - 1 if hi < 101 else 100}",
                "n": n,
                "mean_confidence": round(mean_conf, 1) if mean_conf is not None else None,
                "actual_hit_rate": round(hit * 100, 1) if hit is not None else None,
                "note": note,
            }
        )
    return out


def rolling_accuracy(rows: list[dict], n: int) -> float | None:
    if len(rows) < max(5, n // 5):
        # need some data; still compute if at least 5
        if len(rows) < 5:
            return None
    subset = rows[:n] if len(rows) >= n else rows
    return directional_accuracy(subset)


def grade_from_metrics(
    *,
    accuracy: float | None,
    brier: float | None,
    n: int,
    degradation: bool,
    cfg: Settings | None = None,
) -> ReliabilityGrade:
    tier = sample_tier(n, cfg)
    if tier == SampleTier.INSUFFICIENT:
        return ReliabilityGrade.INSUFFICIENT
    if accuracy is None:
        return ReliabilityGrade.INSUFFICIENT
    # Penalize degradation and poor Brier
    score = accuracy * 100
    if brier is not None:
        score -= max(0.0, (brier - 0.2) * 40)
    if degradation:
        score -= 8
    if tier == SampleTier.PROVISIONAL:
        score -= 3
    if score >= 88:
        return ReliabilityGrade.S if n >= 500 and not degradation else ReliabilityGrade.A_PLUS
    if score >= 82:
        return ReliabilityGrade.A
    if score >= 78:
        return ReliabilityGrade.A_MINUS
    if score >= 72:
        return ReliabilityGrade.B_PLUS
    if score >= 65:
        return ReliabilityGrade.B
    if score >= 55:
        return ReliabilityGrade.C
    if score >= 45:
        return ReliabilityGrade.D
    return ReliabilityGrade.F


def detect_degradation(hist: float | None, last100: float | None, last50: float | None, last20: float | None) -> bool:
    if hist is None or last20 is None:
        return False
    # Clear drop from long-run to recent
    if last50 is not None and hist - last50 >= 0.10 and last20 <= last50:
        return True
    if last100 is not None and hist - last20 >= 0.15:
        return True
    if last20 < 0.55 and hist >= 0.70:
        return True
    return False


def build_reliability_report(
    rows: list[dict],
    *,
    scope: str,
    key: str,
    cfg: Settings | None = None,
) -> ReliabilityReport:
    # rows expected newest-first
    acc = directional_accuracy(rows)
    brier = brier_score(rows)
    last20 = rolling_accuracy(rows, 20)
    last50 = rolling_accuracy(rows, 50)
    last100 = rolling_accuracy(rows, 100)
    deg = detect_degradation(acc, last100, last50, last20)
    n = len(rows)
    grade = grade_from_metrics(accuracy=acc, brier=brier, n=n, degradation=deg, cfg=cfg)
    cal = calibration_buckets(rows)
    # Summarize calibration
    over = sum(1 for c in cal if c["note"] == "OVERCONFIDENT")
    cal_note = "OVERCONFIDENT" if over >= 2 else ("GOOD" if any(c["note"] == "GOOD_CALIBRATION" for c in cal) else "LIMITED_DATA")
    return ReliabilityReport(
        scope=scope,
        key=key,
        grade=grade.value,
        directional_accuracy=round(acc, 4) if acc is not None else None,
        historical_accuracy_pct=round(acc * 100, 1) if acc is not None else None,
        calibration_note=cal_note,
        brier_score=round(brier, 4) if brier is not None else None,
        sample_size=n,
        sample_tier=sample_tier(n, cfg).value,
        last_20=round(last20 * 100, 1) if last20 is not None else None,
        last_50=round(last50 * 100, 1) if last50 is not None else None,
        last_100=round(last100 * 100, 1) if last100 is not None else None,
        degradation=deg,
        mae=round(mae(rows), 3) if mae(rows) is not None else None,
    )


def leaderboard(rows: list[dict], group_key: str = "strategy") -> list[dict]:
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[str(r.get(group_key) or "unknown")].append(r)
    board = []
    for k, subset in groups.items():
        rep = build_reliability_report(subset, scope=group_key, key=k)
        board.append(
            {
                **rep.to_dict(),
                "rmse": round(rmse(subset), 3) if rmse(subset) is not None else None,
            }
        )
    board.sort(key=lambda x: (x["sample_size"] < 50, -(x["historical_accuracy_pct"] or 0)))
    return board


def pick_champion(board: list[dict]) -> dict | None:
    """OOS-style champion: only VALIDATED+ tiers with no degradation."""
    eligible = [
        b
        for b in board
        if b.get("sample_tier") in {SampleTier.VALIDATED.value, SampleTier.HIGH_CONFIDENCE.value}
        and not b.get("degradation")
        and (b.get("historical_accuracy_pct") or 0) >= 60
    ]
    if not eligible:
        return None
    eligible.sort(key=lambda x: (-(x.get("historical_accuracy_pct") or 0), -x.get("sample_size", 0)))
    champ = dict(eligible[0])
    champ["champion"] = True
    champ["note"] = "CURRENT CHAMPION by out-of-sample style validated sample only."
    return champ
