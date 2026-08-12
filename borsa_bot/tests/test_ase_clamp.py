from agentic_se.playground import clamp_non_negative

def test_clamp_negative():
    assert clamp_non_negative(-3) == 0

def test_clamp_positive():
    assert clamp_non_negative(4) == 4
