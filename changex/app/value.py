"""CHANGE X value units — all server-side math uses Mandal (smallest unit).

1 Madalyon = 254 Dirhem
1 Dirhem   = 254 Mandal
1 Madalyon = 64_516 Mandal
"""

from __future__ import annotations

from dataclasses import dataclass

MANDAL_PER_DIRHEM = 254
DIRHEM_PER_MADALYON = 254
MANDAL_PER_MADALYON = MANDAL_PER_DIRHEM * DIRHEM_PER_MADALYON  # 64516


@dataclass(frozen=True)
class ValueBreakdown:
    madalyon: int
    dirhem: int
    mandal: int
    total_mandal: int

    def as_dict(self) -> dict:
        return {
            "madalyon": self.madalyon,
            "dirhem": self.dirhem,
            "mandal": self.mandal,
            "total_mandal": self.total_mandal,
            # Explicit: not real money
            "is_real_money": False,
            "currency_note": "Platform içi değer birimi — gerçek para değildir",
        }


def to_mandal(*, madalyon: int = 0, dirhem: int = 0, mandal: int = 0) -> int:
    if madalyon < 0 or dirhem < 0 or mandal < 0:
        raise ValueError("Değer negatif olamaz")
    return madalyon * MANDAL_PER_MADALYON + dirhem * MANDAL_PER_DIRHEM + mandal


def from_mandal(total: int) -> ValueBreakdown:
    if total < 0:
        raise ValueError("Değer negatif olamaz")
    madalyon, rem = divmod(total, MANDAL_PER_MADALYON)
    dirhem, mandal = divmod(rem, MANDAL_PER_DIRHEM)
    return ValueBreakdown(
        madalyon=madalyon,
        dirhem=dirhem,
        mandal=mandal,
        total_mandal=total,
    )


def difference(a_mandal: int, b_mandal: int) -> dict:
    """Server-side gap between two offer sides. Not payable in real money."""
    gap = a_mandal - b_mandal
    return {
        "a_total_mandal": a_mandal,
        "b_total_mandal": b_mandal,
        "gap_mandal": gap,
        "gap": from_mandal(abs(gap)).as_dict(),
        "exact_match": gap == 0,
        "a_ahead": gap > 0,
        "settlement": "Fark gerçek para ile kapatılamaz. Ürün ekleyin/çıkarın veya yeni teklif oluşturun.",
    }
