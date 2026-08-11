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
    MARKET = "market"
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
    r"(adım neydi|ismim neydi|adımı hatırlıyor|risk tercihim neydi|"
    r"hangi hisseleri|ne biliyorsun|ne hatırlıyorsun)",
    re.I,
)
MATH_RE = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*([+\-*/x×])\s*(-?\d+(?:[.,]\d+)?)\s*(?:kaç|kac)?\s*\??\s*$",
    re.I,
)
MARKET_RE = re.compile(
    r"\b(hisse|borsa|bist|endeks|portföy|yatırım|temettü|foy|stop.?loss|risk|"
    r"nasdaq|sp500|s&p|altın|dolar|euro|kripto|bitcoin|eth|"
    r"thyao|asels|garan|eregl|bim as|akbnk|sahol)\b",
    re.I,
)
SYMBOL_RE = re.compile(r"\b([A-Z]{3,5})\b")
_SYMBOL_STOPWORDS = {
    "NASIL",
    "NEDEN",
    "HANGI",
    "HANGİ",
    "KADAR",
    "ICIN",
    "İÇİN",
    "BENCE",
    "BELKI",
    "BELKİ",
    "SONRA",
    "ONCE",
    "ÖNCE",
    "BUGUN",
    "BUGÜN",
    "YARIN",
    "SIMDI",
    "ŞİMDİ",
    "MERHA",
    "SELAM",
    "RISK",
    "RISKI",
}


def extract_symbols(message: str) -> list[str]:
    found = []
    for symbol in SYMBOL_RE.findall((message or "").upper()):
        if symbol in _SYMBOL_STOPWORDS:
            continue
        if symbol not in found:
            found.append(symbol)
    return found


def classify(message: str) -> Intent:
    text = (message or "").strip()
    if not text:
        return Intent.CHAT
    if MATH_RE.match(text):
        return Intent.MATH
    if MEMORY_QUERY_RE.search(text):
        return Intent.MEMORY_QUERY
    if re.search(
        r"(?:benim adım|adım|ismim|risk tercihim|takip ettiğim hisse|beni .+ diye)",
        text,
        re.I,
    ):
        return Intent.MEMORY_TEACH
    if MARKET_RE.search(text) or extract_symbols(text):
        return Intent.MARKET
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
        if op == "+":
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
        return (
            f"Merhaba {user_name}. Ben Borsa — AI borsa asistanın. "
            "Hisse, risk veya portföy hakkında sorabilirsin."
        )
    return (
        "Merhaba. Ben Borsa — AI tabanlı borsa asistanın. "
        "Bir hisse, endeks veya risk sorusuyla başlayabilirsin."
    )


def empathy_reply(message: str) -> str:
    lower = message.lower()
    if "kaybettim" in lower or "zarar" in lower:
        return (
            "Zarar görmek zor. Panikle karar verme. "
            "İstersen pozisyonu ve riskini birlikte çerçeveleyelim — yatırım tavsiyesi değil, düşünme yardımı."
        )
    if "stres" in lower or "panik" in lower:
        return "Piyasa stresi normal. Nefes al — en çok neyi belirsiz buluyorsun?"
    return "Anladım, ağır gelebilir. Ne oldu — kısa anlat, birlikte netleştirelim."


def market_offline_reply(message: str) -> str:
    symbols = extract_symbols(message)
    hint = f" ({', '.join(symbols[:3])})" if symbols else ""
    return (
        f"AI model şu an çevrimdışı; canlı fiyat veremem{hint}. "
        "Bağlanınca temel analiz, risk çerçevesi ve senaryo konuşabiliriz. "
        "Şimdilik: hedef ufuk (kısa/orta/uzun) ve risk toleransını söyle."
    )


def process(
    message: str,
    *,
    memories: dict[str, str] | None = None,
    prefer_llm: bool = True,
) -> BrainResult:
    """AI-first routing: prefer LLM for almost everything; keep safe offline fallbacks."""
    memories = memories or {}
    intent = classify(message)

    if intent == Intent.MATH:
        result = try_math(message)
        if result is not None:
            return BrainResult(intent, result, False, "brain:math")

    if intent == Intent.MEMORY_TEACH:
        return BrainResult(intent, "Tamam, aklımda tuttum.", False, "brain:teach")

    if intent == Intent.MEMORY_QUERY:
        if not memories:
            fallback = (
                "Henüz senin hakkında kaydettiğim bir şey yok. "
                "Risk tercihin veya takip ettiğin hisseleri söyleyebilirsin."
            )
        else:
            labels = {
                "user_name": "adın",
                "preferred_name": "hitap",
                "risk_profile": "risk",
                "watchlist": "takip listesi",
                "city": "şehir",
            }
            bits = [f"{labels.get(k, k)}: {v}" for k, v in memories.items()]
            fallback = "Hatırladıklarım: " + "; ".join(bits)
        return BrainResult(intent, fallback, prefer_llm, "brain:memory")

    if intent == Intent.GREETING:
        name = memories.get("preferred_name") or memories.get("user_name")
        return BrainResult(intent, greeting_reply(name), prefer_llm, "brain:greeting")

    if intent == Intent.EMPATHY:
        return BrainResult(intent, empathy_reply(message), prefer_llm, "brain:empathy")

    if intent == Intent.MARKET:
        return BrainResult(intent, market_offline_reply(message), True, "brain:market")

    return BrainResult(intent, None, True, "brain:llm")


# Backward-compatible alias used by older tests/imports.
def process_deterministic(
    message: str,
    *,
    memories: dict[str, str] | None = None,
) -> BrainResult:
    return process(message, memories=memories, prefer_llm=False)
