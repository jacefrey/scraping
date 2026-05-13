"""DOM ops tests (spec §6.1, §6.2, §6.6)."""
from pathlib import Path
from bs4 import BeautifulSoup
from webpage_to_pdf.dom_ops import (
    inject_base_href,
    strip_selectors,
    apply_article_mask,
)


FIX = Path(__file__).parent / "fixtures"


def test_inject_base_href_adds_tag():
    html = b"<html><head><title>x</title></head><body><p>y</p></body></html>"
    out = inject_base_href(html, base="https://example.com/")
    soup = BeautifulSoup(out, "html.parser")
    base = soup.find("base", href=True)
    assert base is not None
    assert base["href"] == "https://example.com/"


def test_inject_base_href_replaces_existing():
    html = (b"<html><head><base href='https://old.example/'>"
            b"</head><body></body></html>")
    out = inject_base_href(html, base="https://new.example/")
    soup = BeautifulSoup(out, "html.parser")
    bases = soup.find_all("base", href=True)
    assert len(bases) == 1
    assert bases[0]["href"] == "https://new.example/"


def test_inject_base_creates_head_if_missing():
    html = b"<html><body><p>x</p></body></html>"
    out = inject_base_href(html, base="https://example.com/")
    soup = BeautifulSoup(out, "html.parser")
    assert soup.find("base", href=True)["href"] == "https://example.com/"


def test_strip_selectors_removes_matching():
    html = (FIX / "cookie-banner.html").read_bytes()
    out = strip_selectors(html, selectors=[".cookie-banner", "#chat-widget"])
    text = out.decode("utf-8")
    assert "Cookie consent" not in text
    assert "Chat — strip" not in text
    assert "Body." in text


def test_strip_selectors_empty_list_no_op():
    html = (FIX / "cookie-banner.html").read_bytes()
    out = strip_selectors(html, selectors=[])
    assert out == html


def test_article_mask_marks_ancestors_and_descendants():
    html = (FIX / "sample.html").read_bytes()
    out = apply_article_mask(html, selector="#content")
    soup = BeautifulSoup(out, "html.parser")
    # The injected style rule
    style = soup.find("style")
    assert style is not None
    assert "__wpdf_visible__" in style.get_text()

    # The selected node, its ancestors (main, body, html), and its descendants
    # all carry the marker class
    content = soup.find(id="content")
    assert "__wpdf_visible__" in (content.get("class") or [])
    assert "__wpdf_visible__" in (content.parent.get("class") or [])  # main
    h1 = content.find("h1")
    assert "__wpdf_visible__" in (h1.get("class") or [])

    # Footer / header (siblings of main) are NOT marked
    footer = soup.find("footer")
    assert "__wpdf_visible__" not in (footer.get("class") or [])


def test_article_mask_raises_on_missing_selector():
    import pytest
    from webpage_to_pdf.errors import ConvertError
    html = (FIX / "sample.html").read_bytes()
    with pytest.raises(ConvertError):
        apply_article_mask(html, selector="#does-not-exist")
