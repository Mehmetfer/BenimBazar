from changex.app.value import (
    MANDAL_PER_DIRHEM,
    MANDAL_PER_MADALYON,
    difference,
    from_mandal,
    to_mandal,
)
from changex.app.states import InvalidTransition, TradeState, transition


def test_conversion_constants():
    assert MANDAL_PER_DIRHEM == 254
    assert MANDAL_PER_MADALYON == 64516
    assert to_mandal(madalyon=1) == 64516
    assert to_mandal(dirhem=1) == 254
    assert to_mandal(madalyon=1, dirhem=1, mandal=1) == 64516 + 254 + 1


def test_from_mandal_roundtrip():
    total = to_mandal(madalyon=2, dirhem=3, mandal=4)
    b = from_mandal(total)
    assert b.madalyon == 2
    assert b.dirhem == 3
    assert b.mandal == 4
    assert b.as_dict()["is_real_money"] is False


def test_difference_exact_and_gap():
    a = to_mandal(madalyon=100)
    b = to_mandal(madalyon=93)
    d = difference(a, b)
    assert d["exact_match"] is False
    assert d["gap_mandal"] == to_mandal(madalyon=7)
    assert "gerçek para" in d["settlement"].lower() or "Gerçek para" in d["settlement"]


def test_state_machine_valid_and_invalid():
    assert transition(TradeState.DRAFT, TradeState.PENDING) == TradeState.PENDING
    assert transition(TradeState.OFFERED, TradeState.ACCEPTED) == TradeState.ACCEPTED
    try:
        transition(TradeState.COMPLETED, TradeState.OFFERED)
        assert False, "should raise"
    except InvalidTransition:
        pass
