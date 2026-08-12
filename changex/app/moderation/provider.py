"""AI moderation provider abstraction — providers are swappable."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..states import AiModerationResult, POLICY_VERSION, RiskLevel


@dataclass
class ModerationFinding:
    category: str
    confidence: float
    detail: str = ""


@dataclass
class ModerationAssessment:
    result: AiModerationResult
    confidence: float
    risk_level: RiskLevel
    categories: list[str] = field(default_factory=list)
    findings: list[ModerationFinding] = field(default_factory=list)
    policy_version: str = POLICY_VERSION
    provider: str = "heuristic_v1"
    image_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "confidence": self.confidence,
            "risk_level": self.risk_level.value,
            "categories": self.categories,
            "findings": [
                {"category": f.category, "confidence": f.confidence, "detail": f.detail}
                for f in self.findings
            ],
            "policy_version": self.policy_version,
            "provider": self.provider,
            "image_results": self.image_results,
            "error": self.error,
        }


class ModerationProvider(Protocol):
    """Business logic depends on this interface only."""

    name: str

    def moderate_listing(
        self,
        *,
        title: str,
        description: str,
        category: str,
        wanted_items: str = "",
        photo_urls: list[str] | None = None,
        extra_text: str = "",
    ) -> ModerationAssessment: ...

    def moderate_image(self, *, url: str, context: str = "") -> ModerationAssessment: ...


# Keyword / phrase heuristics (Turkish + English). Not exhaustive — decision support only.
_BLOCK_CSAM = [
    "child porn",
    "childporn",
    "csam",
    "çocuk porno",
    "cocuk porno",
    "underage sex",
    "minor porn",
]

_SEXUAL = [
    "porn",
    "pornografi",
    "müstehcen",
    "mustehcen",
    "escort",
    "cinsel hizmet",
    "nude",
    "çıplak",
    "ciplak",
    "onlyfans",
]

_TRAFFICKING = [
    "insan satışı",
    "insan satisi",
    "satılık insan",
    "satilik insan",
    "human trafficking",
    "köle sat",
]

_DRUGS = [
    "kokain",
    "cocaine",
    "eroin",
    "heroin",
    "metamfetamin",
    "meth ",
    "uyuşturucu",
    "uyusturucu",
    "esrar satılık",
    "bonzai",
]

_WEAPONS = [
    "silah satılık",
    "tabanca sat",
    "ak-47",
    "ruhsatsız silah",
    "ruhsatsiz silah",
    "explosive",
    "patlayıcı",
]

_FRAUD = [
    "garanti kazanç",
    "kolay para",
    "phishing",
    "sahte kimlik",
    "fake id",
    "çalıntı",
    "calinti telefon",
    "çalınmış",
]

_HATE_VIOLENCE = [
    "öldüreceğim",
    "oldurecegim",
    "bombala",
    "terör",
    "terror attack",
]

_PII = [
    "tc kimlik",
    "t.c. kimlik",
    "pasaport no",
    "kredi kartı numarası",
    "credit card number",
]


class HeuristicModerationProvider:
    """Local rule-based pre-moderator. Never auto-publishes."""

    name = "heuristic_v1"

    def moderate_listing(
        self,
        *,
        title: str,
        description: str,
        category: str,
        wanted_items: str = "",
        photo_urls: list[str] | None = None,
        extra_text: str = "",
    ) -> ModerationAssessment:
        blob = " ".join(
            [title or "", description or "", category or "", wanted_items or "", extra_text or ""]
        ).lower()
        findings: list[ModerationFinding] = []
        categories: list[str] = []

        def hit(cat: str, phrases: list[str], confidence: float) -> None:
            for p in phrases:
                if p in blob:
                    findings.append(ModerationFinding(cat, confidence, p))
                    if cat not in categories:
                        categories.append(cat)
                    break

        hit("CSAM", _BLOCK_CSAM, 0.99)
        hit("SEXUAL_CONTENT", _SEXUAL, 0.92)
        hit("HUMAN_TRAFFICKING", _TRAFFICKING, 0.97)
        hit("DRUGS", _DRUGS, 0.93)
        hit("WEAPONS", _WEAPONS, 0.9)
        hit("FRAUD_STOLEN", _FRAUD, 0.85)
        hit("VIOLENCE_HATE", _HATE_VIOLENCE, 0.88)
        hit("PII_LEAK", _PII, 0.8)

        image_results: list[dict] = []
        for url in photo_urls or []:
            img = self.moderate_image(url=url, context=blob)
            image_results.append(img.to_dict())
            for f in img.findings:
                findings.append(f)
                if f.category not in categories:
                    categories.append(f.category)

        if "CSAM" in categories or "HUMAN_TRAFFICKING" in categories:
            return ModerationAssessment(
                result=AiModerationResult.BLOCKED,
                confidence=0.99,
                risk_level=RiskLevel.CRITICAL,
                categories=categories,
                findings=findings,
                image_results=image_results,
            )

        if any(c in categories for c in ("SEXUAL_CONTENT", "DRUGS", "WEAPONS")):
            return ModerationAssessment(
                result=AiModerationResult.HIGH_RISK,
                confidence=max((f.confidence for f in findings), default=0.9),
                risk_level=RiskLevel.HIGH,
                categories=categories,
                findings=findings,
                image_results=image_results,
            )

        if categories:
            return ModerationAssessment(
                result=AiModerationResult.REVIEW,
                confidence=max((f.confidence for f in findings), default=0.7),
                risk_level=RiskLevel.MEDIUM,
                categories=categories,
                findings=findings,
                image_results=image_results,
            )

        # Ambiguous / empty photos → REVIEW not SAFE autopass for images
        if photo_urls:
            for url in photo_urls:
                if not url or not str(url).startswith(("http://", "https://", "changex://")):
                    return ModerationAssessment(
                        result=AiModerationResult.REVIEW,
                        confidence=0.55,
                        risk_level=RiskLevel.MEDIUM,
                        categories=["IMAGE_UNVERIFIED"],
                        findings=[
                            ModerationFinding("IMAGE_UNVERIFIED", 0.55, "invalid or missing photo url")
                        ],
                        image_results=image_results,
                    )

        return ModerationAssessment(
            result=AiModerationResult.SAFE,
            confidence=0.91,
            risk_level=RiskLevel.LOW,
            categories=["SAFE"],
            findings=[],
            image_results=image_results,
        )

    def moderate_image(self, *, url: str, context: str = "") -> ModerationAssessment:
        u = (url or "").lower()
        ctx = (context or "").lower()
        findings: list[ModerationFinding] = []
        categories: list[str] = []
        if not u:
            return ModerationAssessment(
                result=AiModerationResult.REVIEW,
                confidence=0.5,
                risk_level=RiskLevel.MEDIUM,
                categories=["IMAGE_MISSING"],
                findings=[ModerationFinding("IMAGE_MISSING", 0.5, "empty url")],
            )
        banned_tokens = ["porn", "nude", "xxx", "gore", "weapon", "drug"]
        for t in banned_tokens:
            if t in u or t in ctx:
                findings.append(ModerationFinding("IMAGE_RISK", 0.8, t))
                categories.append("IMAGE_RISK")
                break
        if findings:
            return ModerationAssessment(
                result=AiModerationResult.HIGH_RISK,
                confidence=0.8,
                risk_level=RiskLevel.HIGH,
                categories=categories,
                findings=findings,
                image_results=[{"url": url, "flagged": True}],
            )
        return ModerationAssessment(
            result=AiModerationResult.SAFE,
            confidence=0.75,
            risk_level=RiskLevel.LOW,
            categories=["SAFE"],
            findings=[],
            image_results=[{"url": url, "flagged": False}],
        )


class UnavailableModerationProvider:
    """Test/fail-safe provider that always errors."""

    name = "unavailable"

    def moderate_listing(self, **kwargs) -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")

    def moderate_image(self, **kwargs) -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")


_PROVIDER: ModerationProvider = HeuristicModerationProvider()


def get_provider() -> ModerationProvider:
    return _PROVIDER


def set_provider(provider: ModerationProvider) -> None:
    global _PROVIDER
    _PROVIDER = provider
