"""Deterministic clock for test injection (spec §8.7)."""
from datetime import datetime, timezone


def _clock() -> datetime:
    """Return current UTC datetime. Tests monkey-patch this at module level."""
    return datetime.now(timezone.utc)
