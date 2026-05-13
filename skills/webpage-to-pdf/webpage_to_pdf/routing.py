"""Source-type detection + PDF-magic check (spec §5.3, §6.2)."""
from __future__ import annotations
import enum
from pathlib import Path
from typing import Union


class SourceKind(enum.Enum):
    URL = "url"
    LOCAL = "local"


def resolve_source(source: Union[str, Path]) -> tuple[SourceKind, object]:
    if isinstance(source, Path):
        return SourceKind.LOCAL, source.expanduser().resolve()
    if isinstance(source, str):
        if source.startswith(("http://", "https://")):
            return SourceKind.URL, source
        if source.startswith("file://"):
            return SourceKind.LOCAL, Path(source[len("file://"):]).expanduser().resolve()
        return SourceKind.LOCAL, Path(source).expanduser().resolve()
    raise TypeError(f"unsupported source type: {type(source).__name__}")


def looks_like_pdf(path: Path) -> bool:
    """Spec §6.2: source.suffix == '.pdf' or first_bytes == b'%PDF'."""
    if path.suffix.lower() == ".pdf":
        return True
    try:
        with path.open("rb") as f:
            head = f.read(4)
    except OSError:
        return False
    return head.startswith(b"%PDF")
