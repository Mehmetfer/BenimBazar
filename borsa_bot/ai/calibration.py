from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalibrationBucket:
    lo: float
    hi: float
    n: int = 0
    wins: int = 0

    @property
    def hit_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0


@dataclass
class CalibrationMonitor:
    """Tracks whether AI confidence matches realized hit rates. Paper/offline only."""

    buckets: list[CalibrationBucket] = field(
        default_factory=lambda: [
            CalibrationBucket(80, 100),
            CalibrationBucket(70, 80),
            CalibrationBucket(60, 70),
            CalibrationBucket(0, 60),
        ]
    )
    confidence_haircut: float = 0.0

    def record(self, confidence: float, won: bool) -> None:
        for b in self.buckets:
            if b.lo <= confidence < b.hi or (b.hi == 100 and confidence == 100):
                b.n += 1
                if won:
                    b.wins += 1
                break
        self._recompute_haircut()

    def _recompute_haircut(self) -> None:
        # If high-confidence bucket underperforms mid bucket, haircut confidence
        hi = next(b for b in self.buckets if b.lo == 80)
        mid = next(b for b in self.buckets if b.lo == 60)
        if hi.n >= 5 and mid.n >= 5 and hi.hit_rate + 0.05 < mid.hit_rate:
            self.confidence_haircut = 0.15
        elif hi.n >= 5 and hi.hit_rate < 0.45:
            self.confidence_haircut = 0.20
        else:
            self.confidence_haircut = 0.0

    def adjust(self, confidence: float) -> float:
        return round(max(5.0, confidence * (1 - self.confidence_haircut)), 1)

    def report(self) -> dict:
        return {
            "haircut": self.confidence_haircut,
            "buckets": [
                {"range": f"{b.lo}-{b.hi}", "n": b.n, "hit_rate": round(b.hit_rate, 3)} for b in self.buckets
            ],
            "note": "Calibration is observational — not a promise of future accuracy.",
        }
