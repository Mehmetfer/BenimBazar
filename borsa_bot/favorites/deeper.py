from __future__ import annotations

"""Deeper analysis for favorites — visibility/depth only. Never upgrades NO_TRADE → BUY."""

from dataclasses import asdict, dataclass, field

from config.models import IndicatorSet, MarketRegime
from fundamental.provider import get_fundamentals, score_fundamentals
from news.analyzer import classify_headline, latest_stub_headline, score_news
from technical.mtf import analyze_mtf, mtf_conflict_risk
from technical.sector import sector_relative_strength


@dataclass
class DeeperFavoriteAnalysis:
    symbol: str
    mtf: dict[str, str]
    mtf_conflict: bool
    mtf_note: str
    sector_rs: float
    sector_score: float
    sector_notes: list[str]
    fundamental_score: float
    fundamental_notes: list[str]
    fundamental_available: bool
    news_score: float
    news_notes: list[str]
    news_available: bool
    correlation_note: str
    historical_setup_note: str
    user_note_echo: str
    disclaimer: str = (
        "Kullanıcı notu objektif veri değildir. Favori olmak AL sinyali demek değildir."
    )
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def run_deeper_analysis(
    *,
    symbol: str,
    bars: list,
    ind: IndicatorSet,
    price: float,
    volume: float,
    sector: str,
    provider,
    user_note: str = "",
    corr_with_book: float = 0.0,
    regime: MarketRegime | None = None,
) -> DeeperFavoriteAnalysis:
    mtf = analyze_mtf(bars, base_tf_minutes=15)
    conflict, penalty, note = mtf_conflict_risk(mtf)
    rs, sector_sc, sector_notes = sector_relative_strength(provider, symbol, sector)
    fund_snap = get_fundamentals(symbol)
    fund_sc, fund_notes = score_fundamentals(fund_snap)
    news = classify_headline(symbol, latest_stub_headline(symbol))
    news_sc, news_notes, _ = score_news(news)
    hist = (
        f"Yapı={ind.structure}; RSI={ind.rsi14:.1f}; ADX={ind.adx14:.1f}; "
        f"VWAP={'üstü' if price > ind.vwap else 'altı'}; "
        f"rejim={(regime.value if regime else 'n/a')}. "
        "Geçmiş setup hit-rate verisi yoksa uydurulmaz."
    )
    corr_note = (
        f"Açık kitap korelasyonu ≈ {corr_with_book:.2f}"
        if corr_with_book
        else "Açık pozisyon yok / korelasyon n/a"
    )
    return DeeperFavoriteAnalysis(
        symbol=symbol,
        mtf=mtf,
        mtf_conflict=conflict,
        mtf_note=note or f"mtf_penalty={penalty}",
        sector_rs=rs,
        sector_score=sector_sc,
        sector_notes=sector_notes,
        fundamental_score=fund_sc,
        fundamental_notes=fund_notes,
        fundamental_available=bool(getattr(fund_snap, "available", False)),
        news_score=news_sc,
        news_notes=news_notes,
        news_available=bool(getattr(news, "available", False)),
        correlation_note=corr_note,
        historical_setup_note=hist,
        user_note_echo=user_note or "",
        extras={"volume": volume, "price": price},
    )
