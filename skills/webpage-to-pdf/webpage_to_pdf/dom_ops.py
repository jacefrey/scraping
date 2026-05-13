"""BeautifulSoup helpers — base href, strip_selectors, article mask (spec §6.1, §6.2, §6.6)."""
from __future__ import annotations
from bs4 import BeautifulSoup
from webpage_to_pdf.errors import ConvertError


_ARTICLE_MASK_CLASS = "__wpdf_visible__"
_ARTICLE_MASK_STYLE = (
    f":not(.{_ARTICLE_MASK_CLASS}) {{ display: none !important; }}\n"
    f".{_ARTICLE_MASK_CLASS} {{ display: revert; }}\n"
)


def inject_base_href(html: bytes, *, base: str) -> bytes:
    """Inject (or replace) a <base href> tag in <head> (spec §6.2)."""
    soup = BeautifulSoup(html, "html.parser")
    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)
    # Remove any existing <base> tags first
    for existing in head.find_all("base"):
        existing.decompose()
    base_tag = soup.new_tag("base", href=base)
    head.insert(0, base_tag)
    return str(soup).encode("utf-8")


def strip_selectors(html: bytes, *, selectors: list[str]) -> bytes:
    """Remove all matching nodes from a working copy (spec §6.6)."""
    if not selectors:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for sel in selectors:
        for hit in soup.select(sel):
            hit.decompose()
    return str(soup).encode("utf-8")


def apply_article_mask(html: bytes, *, selector: str) -> bytes:
    """Mark the selector node + ancestors + descendants with __wpdf_visible__ and
    inject a CSS rule that hides everything else (spec §6.1).
    """
    soup = BeautifulSoup(html, "html.parser")
    target = soup.select_one(selector)
    if target is None:
        raise ConvertError(
            f"article-mode selector {selector!r} matched zero nodes"
        )

    def _add_class(el):
        classes = el.get("class") or []
        if _ARTICLE_MASK_CLASS not in classes:
            el["class"] = classes + [_ARTICLE_MASK_CLASS]

    # Walk ancestors
    cur = target
    while cur is not None and getattr(cur, "name", None) is not None:
        _add_class(cur)
        cur = cur.parent

    # Walk descendants
    for desc in target.find_all(True):
        _add_class(desc)

    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    style_tag = soup.new_tag("style")
    style_tag.string = _ARTICLE_MASK_STYLE
    head.append(style_tag)
    return str(soup).encode("utf-8")
