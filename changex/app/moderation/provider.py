"""AI moderation provider abstraction — providers are swappable.

Business logic depends only on ModerationProvider. Never auto-publishes.
"""

from __future__ import annotations

import time
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
    """Canonical AI moderation payload (decision support only)."""

    result: AiModerationResult  # status alias
    confidence: float
    risk_level: RiskLevel
    categories: list[str] = field(default_factory=list)
    findings: list[ModerationFinding] = field(default_factory=list)
    policy_version: str = POLICY_VERSION
    provider: str = "heuristic_v1"
    model: str = "heuristic-rules-v1"
    timestamp: float = field(default_factory=time.time)
    image_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def status(self) -> str:
        return self.result.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.result.value,
            "result": self.result.value,
            "risk_level": self.risk_level.value,
            "categories": self.categories,
            "confidence": self.confidence,
            "policy_version": self.policy_version,
            "provider": self.provider,
            "model": self.model,
            "timestamp": self.timestamp,
            "findings": [
                {"category": f.category, "confidence": f.confidence, "detail": f.detail}
                for f in self.findings
            ],
            "image_results": self.image_results,
            "error": self.error,
        }


class ModerationProvider(Protocol):
    """Swappable AI/safety provider interface."""

    name: str

    def analyze_text(self, text: str, *, context: str = "") -> ModerationAssessment: ...

    def analyze_image(self, *, url: str, context: str = "") -> ModerationAssessment: ...

    def analyze_listing(
        self,
        *,
        title: str,
        description: str,
        category: str,
        wanted_items: str = "",
        photo_urls: list[str] | None = None,
        extra_text: str = "",
    ) -> ModerationAssessment: ...

    # Back-compat aliases used by service layer
    def moderate_listing(self, **kwargs: Any) -> ModerationAssessment: ...

    def moderate_image(self, *, url: str, context: str = "") -> ModerationAssessment: ...


# Synthetic keyword lists only — never real abuse media in tests/prod heuristics.
_BLOCK_CHILD_SAFETY = [
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


def _merge(a: ModerationAssessment, b: ModerationAssessment) -> ModerationAssessment:
    """Combine assessments — higher risk wins; never upgrades to APPROVED."""
    rank = {
        AiModerationResult.BLOCKED: 4,
        AiModerationResult.HIGH_RISK: 3,
        AiModerationResult.REVIEW: 2,
        AiModerationResult.UNAVAILABLE: 3,
        AiModerationResult.SAFE: 1,
    }
    winner = a if rank.get(a.result, 0) >= rank.get(b.result, 0) else b
    cats = list(dict.fromkeys([*a.categories, *b.categories]))
    findings = [*a.findings, *b.findings]
    images = [*a.image_results, *b.image_results]
    risk_rank = {RiskLevel.CRITICAL: 4, RiskLevel.HIGH: 3, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 1}
    risk = a.risk_level if risk_rank[a.risk_level] >= risk_rank[b.risk_level] else b.risk_level
    conf = max(a.confidence, b.confidence)
    return ModerationAssessment(
        result=winner.result,
        confidence=conf,
        risk_level=risk,
        categories=cats,
        findings=findings,
        policy_version=winner.policy_version,
        provider=winner.provider,
        model=winner.model,
        image_results=images,
        error=a.error or b.error,
    )


class HeuristicModerationProvider:
    """Local rule-based pre-moderator. Never auto-publishes."""

    name = "heuristic_v1"
    model = "heuristic-rules-v1"

    def analyze_text(self, text: str, *, context: str = "") -> ModerationAssessment:
        blob = f"{text or ''} {context or ''}".lower()
        findings: list[ModerationFinding] = []
        categories: list[str] = []

        def hit(cat: str, phrases: list[str], confidence: float) -> None:
            for p in phrases:
                if p in blob:
                    findings.append(ModerationFinding(cat, confidence, p))
                    if cat not in categories:
                        categories.append(cat)
                    break

        hit("CHILD_SAFETY", _BLOCK_CHILD_SAFETY, 0.99)
        hit("SEXUAL_CONTENT", _SEXUAL, 0.92)
        hit("NUDITY", ["nude", "çıplak", "ciplak"], 0.9)
        hit("HUMAN_TRAFFICKING", _TRAFFICKING, 0.97)
        hit("DRUGS", _DRUGS, 0.93)
        hit("WEAPON", _WEAPONS, 0.9)
        hit("ILLEGAL_GOODS", _WEAPONS + _DRUGS, 0.88)
        hit("FRAUD", _FRAUD, 0.85)
        hit("STOLEN_GOODS", ["çalıntı", "calinti", "çalınmış", "stolen"], 0.85)
        hit("VIOLENCE", _HATE_VIOLENCE, 0.88)
        hit("HATE", _HATE_VIOLENCE, 0.88)
        hit("PERSONAL_DATA", _PII, 0.8)
        hit("DANGEROUS_GOODS", ["patlayıcı", "explosive", "tehlikeli madde"], 0.87)

        if "CHILD_SAFETY" in categories or "HUMAN_TRAFFICKING" in categories:
            return ModerationAssessment(
                result=AiModerationResult.BLOCKED,
                confidence=0.99,
                risk_level=RiskLevel.CRITICAL,
                categories=categories,
                findings=findings,
                provider=self.name,
                model=self.model,
            )
        if any(
            c in categories
            for c in ("SEXUAL_CONTENT", "NUDITY", "DRUGS", "WEAPON", "ILLEGAL_GOODS", "DANGEROUS_GOODS")
        ):
            return ModerationAssessment(
                result=AiModerationResult.HIGH_RISK,
                confidence=max((f.confidence for f in findings), default=0.9),
                risk_level=RiskLevel.HIGH,
                categories=categories,
                findings=findings,
                provider=self.name,
                model=self.model,
            )
        if categories:
            return ModerationAssessment(
                result=AiModerationResult.REVIEW,
                confidence=max((f.confidence for f in findings), default=0.7),
                risk_level=RiskLevel.MEDIUM,
                categories=categories,
                findings=findings,
                provider=self.name,
                model=self.model,
            )
        return ModerationAssessment(
            result=AiModerationResult.SAFE,
            confidence=0.91,
            risk_level=RiskLevel.LOW,
            categories=["SAFE"],
            findings=[],
            provider=self.name,
            model=self.model,
        )

    def analyze_image(self, *, url: str, context: str = "") -> ModerationAssessment:
        return self.moderate_image(url=url, context=context)

    def analyze_listing(
        self,
        *,
        title: str,
        description: str,
        category: str,
        wanted_items: str = "",
        photo_urls: list[str] | None = None,
        extra_text: str = "",
    ) -> ModerationAssessment:
        return self.moderate_listing(
            title=title,
            description=description,
            category=category,
            wanted_items=wanted_items,
            photo_urls=photo_urls,
            extra_text=extra_text,
        )

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
        text = " ".join(
            [title or "", description or "", category or "", wanted_items or "", extra_text or ""]
        )
        assessment = self.analyze_text(text)
        image_results: list[dict] = []
        for url in photo_urls or []:
            img = self.analyze_image(url=url, context=text)
            image_results.append(img.to_dict())
            assessment = _merge(assessment, img)
        assessment.image_results = image_results

        if photo_urls:
            for url in photo_urls:
                if not url or not str(url).startswith(("http://", "https://", "changex://")):
                    unverified = ModerationAssessment(
                        result=AiModerationResult.REVIEW,
                        confidence=0.55,
                        risk_level=RiskLevel.MEDIUM,
                        categories=["IMAGE_UNVERIFIED"],
                        findings=[
                            ModerationFinding(
                                "IMAGE_UNVERIFIED", 0.55, "invalid or missing photo url"
                            )
                        ],
                        provider=self.name,
                        model=self.model,
                        image_results=image_results,
                    )
                    return _merge(assessment, unverified)
        return assessment

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
                provider=self.name,
                model=self.model,
            )
        banned_tokens = ["porn", "nude", "xxx", "gore", "weapon", "drug", "csam"]
        for t in banned_tokens:
            if t in u or t in ctx:
                cat = "CHILD_SAFETY" if t == "csam" else "IMAGE_RISK"
                findings.append(ModerationFinding(cat, 0.8, t))
                categories.append(cat)
                break
        if "CHILD_SAFETY" in categories:
            return ModerationAssessment(
                result=AiModerationResult.BLOCKED,
                confidence=0.99,
                risk_level=RiskLevel.CRITICAL,
                categories=categories,
                findings=findings,
                provider=self.name,
                model=self.model,
                image_results=[{"url": url, "flagged": True}],
            )
        if findings:
            return ModerationAssessment(
                result=AiModerationResult.HIGH_RISK,
                confidence=0.8,
                risk_level=RiskLevel.HIGH,
                categories=categories,
                findings=findings,
                provider=self.name,
                model=self.model,
                image_results=[{"url": url, "flagged": True}],
            )
        return ModerationAssessment(
            result=AiModerationResult.SAFE,
            confidence=0.75,
            risk_level=RiskLevel.LOW,
            categories=["SAFE"],
            findings=[],
            provider=self.name,
            model=self.model,
            image_results=[{"url": url, "flagged": False}],
        )


class UnavailableModerationProvider:
    """Test/fail-safe provider that always errors."""

    name = "unavailable"
    model = "none"

    def analyze_text(self, text: str, *, context: str = "") -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")

    def analyze_image(self, *, url: str, context: str = "") -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")

    def analyze_listing(self, **kwargs: Any) -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")

    def moderate_listing(self, **kwargs: Any) -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")

    def moderate_image(self, **kwargs: Any) -> ModerationAssessment:
        raise RuntimeError("moderation provider unavailable")


class TimeoutModerationProvider:
    """Simulates AI timeout for fail-safe tests."""

    name = "timeout"
    model = "none"

    def analyze_text(self, text: str, *, context: str = "") -> ModerationAssessment:
        raise TimeoutError("moderation provider timeout")

    def analyze_image(self, *, url: str, context: str = "") -> ModerationAssessment:
        raise TimeoutError("moderation provider timeout")

    def analyze_listing(self, **kwargs: Any) -> ModerationAssessment:
        raise TimeoutError("moderation provider timeout")

    def moderate_listing(self, **kwargs: Any) -> ModerationAssessment:
        raise TimeoutError("moderation provider timeout")

    def moderate_image(self, **kwargs: Any) -> ModerationAssessment:
        raise TimeoutError("moderation provider timeout")


class MalformedModerationProvider:
    """Returns invalid confidence to exercise fail-safe validation."""

    name = "malformed"
    model = "broken"

    def analyze_text(self, text: str, *, context: str = "") -> ModerationAssessment:
        return ModerationAssessment(
            result=AiModerationResult.SAFE,
            confidence=float("nan"),
            risk_level=RiskLevel.LOW,
            categories=["SAFE"],
            provider=self.name,
            model=self.model,
        )

    def analyze_image(self, *, url: str, context: str = "") -> ModerationAssessment:
        return self.analyze_text("")

    def analyze_listing(self, **kwargs: Any) -> ModerationAssessment:
        return self.analyze_text(kwargs.get("title", ""))

    def moderate_listing(self, **kwargs: Any) -> ModerationAssessment:
        return self.analyze_listing(**kwargs)

    def moderate_image(self, **kwargs: Any) -> ModerationAssessment:
        return self.analyze_image(**kwargs)


_PROVIDER: ModerationProvider = HeuristicModerationProvider()


def get_provider() -> ModerationProvider:
    return _PROVIDER


def set_provider(provider: ModerationProvider) -> None:
    global _PROVIDER
    _PROVIDER = provider


def validate_assessment(assessment: ModerationAssessment) -> ModerationAssessment:
    """Reject malformed AI payloads — force UNAVAILABLE (no publication)."""
    conf = assessment.confidence
    if conf is None or conf != conf or conf < 0 or conf > 1:  # NaN check via conf != conf
        return ModerationAssessment(
            result=AiModerationResult.UNAVAILABLE,
            confidence=0.0,
            risk_level=RiskLevel.HIGH,
            categories=["MALFORMED_RESPONSE"],
            findings=[],
            provider=assessment.provider,
            model=assessment.model,
            error="invalid confidence",
            policy_version=assessment.policy_version,
        )
    if assessment.result is None:
        return ModerationAssessment(
            result=AiModerationResult.UNAVAILABLE,
            confidence=0.0,
            risk_level=RiskLevel.HIGH,
            categories=["MALFORMED_RESPONSE"],
            error="missing status",
            provider=assessment.provider,
            model=assessment.model,
        )
    return assessment
