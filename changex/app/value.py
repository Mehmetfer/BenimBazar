"""CHANGE X canonical value system.

All economic amounts are stored and computed as integer mandal_units.
No floating point. No real-money currencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MANDAL_PER_DIRHEM = 254
DIRHEM_PER_MADALYON = 254
MANDAL_PER_MADALYON = MANDAL_PER_DIRHEM * DIRHEM_PER_MADALYON  # 64_516

# Soft ceiling to catch overflow / abuse (still integer-safe).
MAX_MANDAL_UNITS = 10**15


class ChangeValueError(ValueError):
    """Invalid CHANGE X value input."""


@dataclass(frozen=True, slots=True)
class ChangeValue:
    """Immutable value object backed by canonical mandal_units."""

    mandal_units: int

    def __post_init__(self) -> None:
        if not isinstance(self.mandal_units, int) or isinstance(self.mandal_units, bool):
            raise ChangeValueError("mandal_units must be int")
        if self.mandal_units < 0:
            raise ChangeValueError("negatif değer kabul edilmez")
        if self.mandal_units > MAX_MANDAL_UNITS:
            raise ChangeValueError("değer taşması (overflow)")

    # ---- constructors ----

    @classmethod
    def zero(cls) -> ChangeValue:
        return cls(0)

    @classmethod
    def from_units(
        cls,
        *,
        madalyon: int = 0,
        dirhem: int = 0,
        mandal: int = 0,
    ) -> ChangeValue:
        for name, raw in (("madalyon", madalyon), ("dirhem", dirhem), ("mandal", mandal)):
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise ChangeValueError(f"{name} tam sayı olmalı (float/decimal yasak)")
            if raw < 0:
                raise ChangeValueError("negatif değer kabul edilmez")
        total = madalyon * MANDAL_PER_MADALYON + dirhem * MANDAL_PER_DIRHEM + mandal
        if total > MAX_MANDAL_UNITS:
            raise ChangeValueError("değer taşması (overflow)")
        return cls(total)

    @classmethod
    def from_mandal_units(cls, units: Any) -> ChangeValue:
        if isinstance(units, bool) or not isinstance(units, int):
            raise ChangeValueError("mandal_units tam sayı olmalı")
        return cls(units)

    @classmethod
    def parse(cls, payload: Any) -> ChangeValue:
        """Parse API/body payload into ChangeValue. Rejects floats and strings-with-decimal."""
        if payload is None:
            return cls.zero()
        if isinstance(payload, ChangeValue):
            return payload
        if isinstance(payload, bool):
            raise ChangeValueError("geçersiz değer")
        if isinstance(payload, int):
            return cls.from_mandal_units(payload)
        if isinstance(payload, float):
            raise ChangeValueError("floating-point değer kabul edilmez")
        if isinstance(payload, str):
            s = payload.strip().replace(",", ".")
            if "." in s:
                raise ChangeValueError("ondalıklı değer kabul edilmez")
            if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
                raise ChangeValueError("geçersiz sayı")
            return cls.from_mandal_units(int(s))
        if isinstance(payload, dict):
            if "mandal_units" in payload and payload["mandal_units"] is not None:
                return cls.from_mandal_units(_require_int(payload["mandal_units"], "mandal_units"))
            return cls.from_units(
                madalyon=_require_int(payload.get("madalyon", 0), "madalyon"),
                dirhem=_require_int(payload.get("dirhem", 0), "dirhem"),
                mandal=_require_int(payload.get("mandal", 0), "mandal"),
            )
        raise ChangeValueError("değer parse edilemedi")

    # ---- breakdown / format ----

    @property
    def madalyon(self) -> int:
        return self.mandal_units // MANDAL_PER_MADALYON

    @property
    def dirhem(self) -> int:
        rem = self.mandal_units % MANDAL_PER_MADALYON
        return rem // MANDAL_PER_DIRHEM

    @property
    def mandal(self) -> int:
        return self.mandal_units % MANDAL_PER_DIRHEM

    def normalize(self) -> ChangeValue:
        return self  # already canonical

    def components(self) -> dict[str, int]:
        return {
            "madalyon": self.madalyon,
            "dirhem": self.dirhem,
            "mandal": self.mandal,
            "mandal_units": self.mandal_units,
        }

    def format(self) -> str:
        return f"{self.madalyon} Madalyon · {self.dirhem} Dirhem · {self.mandal} Mandal"

    def format_gap(self) -> str:
        return f"{self.format()} değer farkı"

    def serialize(self) -> dict[str, Any]:
        return {
            **self.components(),
            "display": self.format(),
            "is_real_money": False,
            "unit_system": "CHANGE_X",
            "note": "Platform içi takas değeri — gerçek para değildir",
        }

    # ---- arithmetic / compare ----

    def add(self, other: ChangeValue) -> ChangeValue:
        total = self.mandal_units + other.mandal_units
        if total > MAX_MANDAL_UNITS:
            raise ChangeValueError("değer taşması (overflow)")
        return ChangeValue(total)

    def subtract(self, other: ChangeValue) -> ChangeValue:
        if other.mandal_units > self.mandal_units:
            raise ChangeValueError("sonuç negatif olamaz")
        return ChangeValue(self.mandal_units - other.mandal_units)

    def compare(self, other: ChangeValue) -> int:
        return (self.mandal_units > other.mandal_units) - (self.mandal_units < other.mandal_units)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChangeValue):
            return NotImplemented
        return self.mandal_units == other.mandal_units

    def __lt__(self, other: ChangeValue) -> bool:
        return self.mandal_units < other.mandal_units

    def __add__(self, other: ChangeValue) -> ChangeValue:
        return self.add(other)

    def __sub__(self, other: ChangeValue) -> ChangeValue:
        return self.subtract(other)


def _require_int(raw: Any, name: str) -> int:
    if isinstance(raw, bool) or isinstance(raw, float):
        raise ChangeValueError(f"{name} floating-point/bool kabul edilmez")
    if isinstance(raw, str):
        s = raw.strip()
        if "." in s or "," in s:
            raise ChangeValueError(f"{name} ondalıklı olamaz")
        if s.startswith("-"):
            raise ChangeValueError("negatif değer kabul edilmez")
        if not s.isdigit():
            raise ChangeValueError(f"{name} geçersiz")
        return int(s)
    if not isinstance(raw, int):
        raise ChangeValueError(f"{name} tam sayı olmalı")
    if raw < 0:
        raise ChangeValueError("negatif değer kabul edilmez")
    return raw


def value_gap(a: ChangeValue, b: ChangeValue) -> dict[str, Any]:
    """Canonical gap between two sides. Never expressed as real money."""
    gap_units = a.mandal_units - b.mandal_units
    abs_gap = ChangeValue(abs(gap_units))
    return {
        "a": a.serialize(),
        "b": b.serialize(),
        "value_gap": abs_gap.serialize(),
        "value_gap_mandal_units": gap_units,
        "value_gap_display": abs_gap.format_gap(),
        "exact_match": gap_units == 0,
        "a_ahead": gap_units > 0,
        "settlement": (
            "Fark gerçek para ile kapatılamaz. "
            "Ürün ekleyin/çıkarın veya yeni teklif oluşturun."
        ),
    }


# Back-compat aliases used by older call sites
def to_mandal(*, madalyon: int = 0, dirhem: int = 0, mandal: int = 0) -> int:
    return ChangeValue.from_units(madalyon=madalyon, dirhem=dirhem, mandal=mandal).mandal_units


def from_mandal(total: int) -> dict[str, Any]:
    return ChangeValue.from_mandal_units(total).serialize()


def difference(a_mandal: int, b_mandal: int) -> dict[str, Any]:
    return value_gap(
        ChangeValue.from_mandal_units(a_mandal),
        ChangeValue.from_mandal_units(b_mandal),
    )
