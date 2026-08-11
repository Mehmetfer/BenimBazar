from __future__ import annotations

from config.models import NewsItem, NewsSentiment


def classify_headline(symbol: str, headline: str | None) -> NewsItem:
    if not headline:
        return NewsItem(
            symbol=symbol,
            headline="",
            sentiment=NewsSentiment.NEUTRAL,
            importance=0.0,
            confidence=0.0,
            price_impact=0.0,
            sector_impact=0.0,
            validity_hours=0.0,
            available=False,
        )
    text = headline.lower()
    if any(w in text for w in ("soruşturma", "ceza", "iflas", "konkordato", "manipülasyon")):
        sent = NewsSentiment.HIGH_RISK
        impact = -0.7
        conf = 0.7
    elif any(w in text for w in ("zarar", "dava", "iptal", "erteleme")):
        sent = NewsSentiment.NEGATIVE
        impact = -0.35
        conf = 0.55
    elif any(w in text for w in ("rekor", "kâr", "temettü", "sözleşme", "büyüme")):
        sent = NewsSentiment.POSITIVE
        impact = 0.35
        conf = 0.55
    elif any(w in text for w in ("iddia", "söylenti", "belirsiz")):
        sent = NewsSentiment.UNCERTAIN
        impact = 0.0
        conf = 0.25
    else:
        sent = NewsSentiment.NEUTRAL
        impact = 0.0
        conf = 0.4
    return NewsItem(
        symbol=symbol,
        headline=headline,
        sentiment=sent,
        importance=min(1.0, abs(impact) + 0.3),
        confidence=conf,
        price_impact=impact,
        sector_impact=impact * 0.4,
        validity_hours=24.0,
        available=True,
    )


def score_news(item: NewsItem) -> tuple[float, list[str], bool]:
    """Returns score, notes, block_trade."""
    if not item.available:
        return 50.0, ["news_unavailable_neutral"], False
    if item.sentiment == NewsSentiment.UNCERTAIN:
        return 35.0, ["uncertain_news_block"], True
    if item.sentiment == NewsSentiment.HIGH_RISK:
        return 15.0, ["high_risk_news_block"], True
    if item.sentiment == NewsSentiment.POSITIVE:
        return 70 + 20 * item.confidence, ["positive_news"], False
    if item.sentiment == NewsSentiment.NEGATIVE:
        return 30 - 10 * item.importance, ["negative_news"], False
    return 50.0, ["neutral_news"], False


def latest_stub_headline(symbol: str) -> str | None:
    # No live KAP feed in MVP — return None (honest). Callers treat as unavailable.
    return None
