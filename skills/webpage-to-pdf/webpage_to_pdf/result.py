"""ConvertResult — public return type from convert() (spec §6.1, §6.2)."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConvertResult:
    pdf_path: Path
    source_html_path: Path | None
    rendered_html_path: Path | None
    render_mode: str | None
    live_double_fetch: bool | None
    passthrough: bool
