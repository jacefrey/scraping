"""ConvertResult — public return type from convert() (spec §5.2, §5.9)."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConvertResult:
    """Return value from webpage_to_md.convert().

    For HTML inputs: markdown_path + source_path set, pdf_path=None, md_generated=True.
    For PDF responses (v0.1 — passthrough deferred to v0.2): pdf_path set,
    markdown_path=None, md_generated=False (spec §5.9 callout).
    """
    markdown_path: Path | None
    source_path: Path | None
    pdf_path: Path | None
    md_generated: bool
    content_type: str | None
