"""Deterministic clock for test injection (spec §8.7)."""
from datetime import datetime, timezone


def _clock() -> datetime:
    return datetime.now(timezone.utc)
