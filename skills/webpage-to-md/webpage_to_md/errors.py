"""Exception hierarchy for webpage-to-md (spec §5.6, §8.4)."""
from __future__ import annotations
from typing import Any


class ConvertError(Exception):
    """Base exception for webpage-to-md. Catch this for any conversion failure."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.context = context


class ConvertConfigError(ConvertError):
    """Raised when configuration requests a behavior the skill cannot satisfy.

    Distinct from NotImplementedError because the failure is a user-level config
    issue (e.g. requesting a deferred Readify-based extraction strategy), not
    a missing implementation in the skill itself (spec §5.6).
    """
