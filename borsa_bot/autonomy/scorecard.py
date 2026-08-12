"""FAZ 8 — Evidence-based autonomy scorecard. No score without proof."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from autonomy.levels import LevelResult, LevelStatus


@dataclass
class CriterionScore:
    id: int
    name: str
    score: float  # 0–10
    evidence: list[str] = field(default_factory=list)
    limit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomyScorecard:
    overall: float
    criteria: list[CriterionScore]
    level_results: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = ""
    starting: float = 5.6
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "starting": self.starting,
            "overall": self.overall,
            "verdict": self.verdict,
            "criteria": [c.to_dict() for c in self.criteria],
            "level_results": self.level_results,
            "notes": self.notes,
        }


def score_autonomy(
    *,
    level_results: list[LevelResult],
    gates_ok: bool,
    lesson_count: int,
    self_review_ok: bool,
    baseline_pass: int,
    baseline_fail: int,
    live_locked: bool,
) -> AutonomyScorecard:
    """Score only from measured signals — never inflate."""
    passed_levels = {r.level for r in level_results if r.status == LevelStatus.PASS}
    failed_levels = {r.level for r in level_results if r.status == LevelStatus.FAIL}

    def lvl_pass(n: int) -> bool:
        return n in passed_levels

    criteria = [
        CriterionScore(
            1,
            "Hata tespiti",
            7.0 if self_review_ok and gates_ok else 5.0,
            evidence=[
                f"self_review_ok={self_review_ok}",
                f"gates_ok={gates_ok}",
                "self_review catches syntax + LIVE unlock patterns",
            ],
            limit="Sessiz domain hataları hâlâ test coverage'a bağlı",
        ),
        CriterionScore(
            2,
            "Hata düzeltme",
            7.0 if baseline_fail == 0 and gates_ok else (6.0 if gates_ok else 4.5),
            evidence=[
                f"baseline_pass={baseline_pass}",
                f"baseline_fail={baseline_fail}",
                "failure protocol module + gate retest loop",
            ],
            limit="Belirsiz ürün kararlarında insan gerekir",
        ),
        CriterionScore(
            3,
            "Eksik yüzey tespiti",
            7.0 if lvl_pass(5) else 4.5,
            evidence=["completeness.scan_symbol", "scan_changed_exports", f"L5={lvl_pass(5)}"],
            limit="AST/text scan; dynamic dispatch kaçabilir",
        ),
        CriterionScore(
            4,
            "Gerçek test çalıştırma",
            8.5 if baseline_pass >= 250 else 6.0,
            evidence=[f"pytest baseline ~{baseline_pass} passed", "gates run real pytest nodes"],
            limit="Bazı integration'lar environment bağımlı",
        ),
        CriterionScore(
            5,
            "Root-cause / retry",
            7.0 if lvl_pass(2) and lvl_pass(4) else 5.0,
            evidence=["failure protocol steps tested", f"L2={lvl_pass(2)} L4={lvl_pass(4)}"],
            limit="Otomatik hipotez üretimi yok — disiplin kod + test",
        ),
        CriterionScore(
            6,
            "Kalıcı öğrenme",
            min(8.0, 5.0 + min(3.0, lesson_count * 0.4)) if lvl_pass(6) else 4.0,
            evidence=[f"lesson_count={lesson_count}", "lesson→regression CI gate", f"L6={lvl_pass(6)}"],
            limit="Self-modifying prod YOK (bilinçli); lesson=data+test",
        ),
        CriterionScore(
            7,
            "Görev parçalama",
            7.0 if gates_ok else 5.0,
            evidence=["LOOP_STEPS enforced", "gates G1–G8"],
            limit="Kapsam şişmesi hâlâ mümkün",
        ),
        CriterionScore(
            8,
            "Level 1→8 ilerleme",
            # Honest: L8 PASS only if acceptance says so AND we don't claim full L8 trading autonomy
            (
                8.0
                if passed_levels >= {1, 2, 3, 4, 5, 6, 7, 8}
                else (6.5 if passed_levels >= {1, 2, 3, 4, 5, 6} else 4.0)
            ),
            evidence=[
                f"passed={sorted(passed_levels)}",
                f"failed={sorted(failed_levels)}",
                "L8 = acceptance tests, not folder presence",
            ],
            limit="Trading self-evolution LIVE kapalı; L8 research/paper kabul",
        ),
        CriterionScore(
            9,
            "Mimari refactor",
            6.0 if gates_ok else 4.0,
            evidence=["autonomy package additive; crypto fail-closed chart fix"],
            limit="Büyük kırılımlı refactor kanıtı bu turda sınırlı",
        ),
        CriterionScore(
            10,
            "İnsan olmadan uçtan uca",
            6.5 if gates_ok and live_locked and lvl_pass(6) else 5.0,
            evidence=[
                f"live_locked={live_locked}",
                "protocol runner produces report without human mid-gate",
            ],
            limit="Muğlak hedef / LIVE onay hâlâ insan",
        ),
    ]

    overall = round(sum(c.score for c in criteria) / len(criteria), 2)

    if not live_locked:
        verdict = "TESTLER YETERSİZ — OTONOMİ SEVİYESİ BELİRLENEMEDİ"
        notes = ["LIVE lock failed — scoring aborted for safety"]
        overall = min(overall, 3.0)
    elif overall >= 8.0 and passed_levels >= {1, 2, 3, 4, 5, 6, 7, 8} and gates_ok:
        verdict = "OTONOMİ 8+ KANITLANDI"
        notes = ["All measured gates + L1–L8 acceptance PASS; LIVE remains locked"]
    elif baseline_pass < 50:
        verdict = "TESTLER YETERSİZ — OTONOMİ SEVİYESİ BELİRLENEMEDİ"
        notes = ["Insufficient pytest evidence"]
    else:
        verdict = "OTONOMİ 8+'A ULAŞMADI"
        notes = [
            f"overall={overall} (need >=8.0 with L1–L8 PASS)",
            f"levels_passed={sorted(passed_levels)}",
            "Claim withheld without full level PASS set",
        ]

    return AutonomyScorecard(
        overall=overall,
        criteria=criteria,
        level_results=[r.to_dict() for r in level_results],
        verdict=verdict,
        starting=5.6,
        notes=notes,
    )
