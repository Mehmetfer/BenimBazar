from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"
    EMPATHY = "empathy"
    MEMORY_QUERY = "memory_query"
    MEMORY_TEACH = "memory_teach"
    MATH = "math"
    QUESTION = "question"
    CHAT = "chat"


@dataclass
class BrainResult:
    intent: Intent
    reply: str | None
    use_llm: bool
    source: str


GREETING_RE = re.compile(
    r"^\s*(merhaba|selam|selamlar|günaydın|iyi akşamlar|iyi geceler|hey|naber|nasılsın|nasilsin)\b",
    re.I,
)
EMPATHY_RE = re.compile(
    r"(üzgün|yalnız|depres|moralim|moralim bozuk|stres|korkuyorum|kaybettim|canım sıkkın|bunaldım|panik)",
    re.I,
)
MEMORY_QUERY_RE = re.compile(
    r"(adım neydi|ismim neydi|adımı hatırlıyor|kedimin adı|nerede yaşıyorum|ne biliyorsun)",
    re.I,
)
MATH_RE = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*([+\-*/x×])\s*(-?\d+(?:[.,]\d+)?)\s*(?:kaç|kac)?\s*\??\s*$",
    re.I,
)


def classify(message: str) -> Intent:
    text = (message or "").strip()
    if not text:
        return Intent.CHAT
    if MATH_RE.match(text):
        return Intent.MATH
    if MEMORY_QUERY_RE.search(text):
        return Intent.MEMORY_QUERY
    if re.search(r"(?:benim adım|adım|ismim|kedimin adı|beni .+ diye)", text, re.I):
        return Intent.MEMORY_TEACH
    if EMPATHY_RE.search(text):
        return Intent.EMPATHY
    if GREETING_RE.search(text):
        return Intent.GREETING
    if text.endswith("?") or re.match(r"^(ne|neden|nasıl|kim|hangi|kaç)\b", text, re.I):
        return Intent.QUESTION
    return Intent.CHAT


def try_math(message: str) -> str | None:
    match = MATH_RE.match(message or "")
    if not match:
        return None
    left = float(match.group(1).replace(",", "."))
    op = match.group(2)
    right = float(match.group(3).replace(",", "."))
    try:
        if op in {"+",}:
            value = left + right
        elif op == "-":
            value = left - right
        elif op in {"*", "x", "×"}:
            value = left * right
        elif op == "/":
            if right == 0:
                return "Sıfıra bölemem."
            value = left / right
        else:
            return None
    except Exception:
        return None
    if value == int(value):
        return str(int(value))
    return f"{value:.4g}"


def greeting_reply(user_name: str | None) -> str:
    if user_name:
        return f"Merhaba {user_name}. Buradayım — ne konuşmak istersin?"
    return "Merhaba. Ben Koca Kafa. Bugün nasılsın?"


def empathy_reply(message: str) -> str:
    lower = message.lower()
    if "yalnız" in lower:
        return "Yalnız hissetmek ağır gelebilir. Yanındayım — biraz anlatmak ister misin?"
    if "kaybettim" in lower:
        return "Üzgünüm. Kaybetmek acıtır. İstersen dinlerim."
    if "stres" in lower or "bunaldım" in lower or "panik" in lower:
        return "Şu an zor görünüyor. Bir nefescik al — ne en çok baskı yapıyor?"
    return "Bu zor bir yerde olmak. Duygularını önemsiyorum. Ne oldu?"


def process_deterministic(
    message: str,
    *,
    memories: dict[str, str] | None = None,
) -> BrainResult:
    memories = memories or {}
    intent = classify(message)

    if intent == Intent.MATH:
        result = try_math(message)
        if result is not None:
            return BrainResult(intent, result, False, "brain:math")

    if intent == Intent.GREETING:
        name = memories.get("preferred_name") or memories.get("user_name")
        return BrainResult(intent, greeting_reply(name), False, "brain:greeting")

    if intent == Intent.EMPATHY:
        return BrainResult(intent, empathy_reply(message), False, "brain:empathy")

    if intent == Intent.MEMORY_QUERY:
        if not memories:
            return BrainResult(
                intent,
                "Henüz senin hakkında kaydettiğim bir şey yok. İstersen adını söyle, aklımda tutayım.",
                False,
                "brain:memory-empty",
            )
        labels = {
            "user_name": "adın",
            "preferred_name": "hitap",
            "cat_name": "kedinin adı",
            "city": "şehir",
        }
        bits = [f"{labels.get(k, k)}: {v}" for k, v in memories.items()]
        return BrainResult(
            intent,
            "Hatırladıklarım: " + "; ".join(bits),
            False,
            "brain:memory",
        )

    if intent == Intent.MEMORY_TEACH:
        return BrainResult(
            intent,
            "Tamam, aklımda tuttum.",
            False,
            "brain:teach",
        )

    return BrainResult(intent, None, True, "brain:llm")
