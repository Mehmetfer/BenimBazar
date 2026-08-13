"""Self-verification target fixture — intentionally BROKEN until sandbox fix."""

MARKER = "BROKEN"


def self_check() -> bool:
    """Intentional defect for F7 controlled self-verification demos/tests."""
    return False  # intentional defect


def answer() -> str:
    return "NOT_READY"
