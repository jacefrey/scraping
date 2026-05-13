"""Source-type detection for convert() (spec §5.3)."""
from __future__ import annotations
import enum
from pathlib import Path
from typing import Union


class SourceKind(enum.Enum):
    URL = "url"
    LOCAL = "local"


def resolve_source(source: Union[str, Path]) -> tuple[SourceKind, object]:
    """Detect whether `source` is a URL or a local file (spec §5.3).

    Returns (SourceKind.URL, url_str) for http(s):// strings,
    or (SourceKind.LOCAL, resolved_path) for everything else.
    """
    if isinstance(source, Path):
        return SourceKind.LOCAL, source.expanduser().resolve()

    if isinstance(source, str):
        if source.startswith(("http://", "https://")):
            return SourceKind.URL, source
        if source.startswith("file://"):
            stripped = source[len("file://"):]
            return SourceKind.LOCAL, Path(stripped).expanduser().resolve()
        return SourceKind.LOCAL, Path(source).expanduser().resolve()

    raise TypeError(f"unsupported source type: {type(source).__name__}")
