"""Stage 2: HTML → Markdown via markdownify (spec §5.5, §5.10)."""
from __future__ import annotations
from typing import Any
from bs4 import BeautifulSoup
from bs4.element import Tag
from markdownify import markdownify, ATX, SETEXT

# Map config heading_style strings → markdownify constants.
# markdownify uses "atx" / "underlined"; the config uses "ATX" / "SETEXT".
_HEADING_STYLE_MAP: dict[str, str] = {
    "ATX": ATX,
    "SETEXT": SETEXT,
    # Accept markdownify's own values too, for forward-compatibility.
    ATX: ATX,
    SETEXT: SETEXT,
}


def _strip_pre_conversion(node: Tag, cfg: dict[str, Any]) -> Tag:
    """Apply strip_classes / strip_selectors / preserve_classes on a *copy*.

    The original node belongs to the caller's working soup; we never mutate it
    in place here. Returns the cleaned copy.
    """
    html_to_md = cfg["convert"]["html_to_md"]
    strip_classes: list[str] = list(html_to_md.get("strip_classes", []) or [])
    strip_selectors: list[str] = list(html_to_md.get("strip_selectors", []) or [])
    preserve_classes: set[str] = set(html_to_md.get("preserve_classes", []) or [])

    cleaned = BeautifulSoup(str(node), "html.parser")

    # 1. strip_selectors: remove anything matching, regardless of class
    for sel in strip_selectors:
        for hit in cleaned.select(sel):
            hit.decompose()

    # 2. strip_classes: remove nodes whose class list intersects, UNLESS the
    # node also has a preserve_classes match (spec §5.10 preserve_classes).
    for klass in strip_classes:
        for hit in list(cleaned.find_all(class_=klass)):
            classes = set(hit.get("class") or [])
            if classes & preserve_classes:
                continue
            hit.decompose()

    return cleaned


def convert_to_markdown(node: Tag, cfg: dict[str, Any]) -> str:
    """Apply strip rules + markdownify (spec §5.5)."""
    cleaned = _strip_pre_conversion(node, cfg)
    raw_style = cfg["convert"]["html_to_md"].get("heading_style", "ATX")
    heading_style = _HEADING_STYLE_MAP.get(raw_style, ATX)
    return markdownify(str(cleaned), heading_style=heading_style)
