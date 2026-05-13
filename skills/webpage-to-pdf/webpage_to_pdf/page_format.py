"""Page-format resolution + 200" auto-fallback (spec §6.4)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from webpage_to_pdf.errors import ConvertError


_DPI = 96
_CONTINUOUS_CAP_IN = 200.0
_SCREEN_WIDTH_IN = 13.33  # 1280 px / 96 dpi
_SCREEN_HEIGHT_IN = 8.33   # 800 px / 96 dpi

_FIXED_FORMATS = {
    "Letter": (8.5, 11.0),
    "A4": (8.27, 11.69),
    "Legal": (8.5, 14.0),
    "screen-paginated": (_SCREEN_WIDTH_IN, _SCREEN_HEIGHT_IN),
}


@dataclass
class ResolvedFormat:
    width_in: float
    height_in: float
    is_continuous: bool
    fell_back: bool
    raw: Any = None


def resolve_page_format(
    page_format: Any,
    *,
    page_height_px: int,
    viewport_width_px: int,
) -> ResolvedFormat:
    """Translate a page_format spec into width/height in inches (spec §6.4).

    Continuous mode caps at 200" — beyond that, auto-fall-back to screen-paginated.
    """
    if isinstance(page_format, dict):
        return ResolvedFormat(
            width_in=0.0, height_in=0.0,
            is_continuous=False, fell_back=False,
            raw=page_format,
        )
    if not isinstance(page_format, str):
        raise ConvertError(f"unsupported page_format type: {type(page_format)}")

    normalized = page_format
    if normalized == "screen":
        normalized = "continuous"

    if normalized == "continuous":
        width_in = round(viewport_width_px / _DPI, 2)
        height_in = round(page_height_px / _DPI, 2)
        if height_in > _CONTINUOUS_CAP_IN:
            return ResolvedFormat(
                width_in=_SCREEN_WIDTH_IN,
                height_in=_SCREEN_HEIGHT_IN,
                is_continuous=False,
                fell_back=True,
                raw=page_format,
            )
        return ResolvedFormat(
            width_in=width_in,
            height_in=height_in,
            is_continuous=True,
            fell_back=False,
            raw=page_format,
        )

    if normalized in _FIXED_FORMATS:
        w, h = _FIXED_FORMATS[normalized]
        return ResolvedFormat(
            width_in=w, height_in=h,
            is_continuous=False, fell_back=False,
            raw=page_format,
        )

    raise ConvertError(f"unknown page_format: {page_format!r}")
