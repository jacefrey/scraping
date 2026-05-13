"""Stage 1: select the content node before MD conversion (spec §5.6)."""
from __future__ import annotations
from bs4 import BeautifulSoup
from webpage_to_md.errors import ConvertConfigError


def select_content_node(
    soup: BeautifulSoup,
    *,
    selector: str | None,
    strategy: str,
):
    """Return the bs4 Tag to convert to Markdown.

    Strategies (spec §5.6):
    - explicit_selector: when `selector` is truthy → soup.select_one(selector)
    - readability: when strategy enables it AND no explicit selector → raise
      ConvertConfigError (deferred to Readify; hook only).
    - body_fallback: main → article → body.
    """
    if selector:
        node = soup.select_one(selector)
        if node is None:
            raise ConvertConfigError(
                f"selector {selector!r} matched zero nodes in the source HTML"
            )
        return node

    if strategy == "selector_then_readability_then_body":
        raise ConvertConfigError(
            "readability strategy requires Readify; not yet shipped. "
            "Use 'selector_then_body' (default) or pass an explicit selector."
        )

    # body_fallback (default)
    node = soup.select_one("main") or soup.select_one("article") or soup.body
    if node is None:
        # Defensive: documents with no <body> are extremely rare but possible.
        node = soup
    return node
