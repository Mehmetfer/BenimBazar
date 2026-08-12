"""CHANGE X matching / exchange-graph package (infrastructure only)."""

from .config import CHANGE_CHAIN_ENABLED, MATCHING_POLICY_VERSION
from .compatibility import CategoryCompatibility, get_compatibility
from .matchability import (
    chain_feature_enabled,
    is_chain_candidate,
    is_public_matchable,
    matchability_report,
)
from .preferences import get_user_preferences, public_preferences_view, set_user_preferences
from .scoring import MatchCandidate, NullScoreProvider, ScoreBreakdown, ScoreProvider
from .wants import WantValidationError, normalize_offer_fields, validate_structured_want

__all__ = [
    "CHANGE_CHAIN_ENABLED",
    "MATCHING_POLICY_VERSION",
    "CategoryCompatibility",
    "get_compatibility",
    "chain_feature_enabled",
    "is_chain_candidate",
    "is_public_matchable",
    "matchability_report",
    "get_user_preferences",
    "public_preferences_view",
    "set_user_preferences",
    "MatchCandidate",
    "NullScoreProvider",
    "ScoreBreakdown",
    "ScoreProvider",
    "WantValidationError",
    "normalize_offer_fields",
    "validate_structured_want",
]
