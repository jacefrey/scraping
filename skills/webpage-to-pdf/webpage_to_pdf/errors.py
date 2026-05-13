"""Exception hierarchy for webpage-to-pdf (spec §8.4)."""
from __future__ import annotations
from typing import Any


class ConvertError(Exception):
    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.context = context
