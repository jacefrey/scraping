"""Stage 2: HTML → Markdown via markdownify (spec §5.5, §5.10)."""
from bs4 import BeautifulSoup
from webpage_to_md.html_to_md import convert_to_markdown


def _cfg(strip_classes=None, strip_selectors=None, preserve_classes=None,
         heading_style="ATX"):
    return {
        "convert": {
            "html_to_md": {
                "strip_classes": strip_classes or [],
                "strip_selectors": strip_selectors or [],
                "preserve_classes": preserve_classes or [],
                "heading_style": heading_style,
            }
        }
    }


def test_basic_html_to_md():
    soup = BeautifulSoup("<div><h1>Hello</h1><p>World</p></div>", "html.parser")
    md = convert_to_markdown(soup.div, _cfg())
    assert "# Hello" in md
    assert "World" in md


def test_strip_classes_removes_nodes():
    soup = BeautifulSoup(
        "<div><p>Keep</p><div class='ad'>Drop me</div><p>Keep too</p></div>",
        "html.parser",
    )
    md = convert_to_markdown(soup.div, _cfg(strip_classes=["ad"]))
    assert "Keep" in md
    assert "Keep too" in md
    assert "Drop me" not in md


def test_strip_selectors_removes_matching():
    soup = BeautifulSoup(
        "<div><p>Body</p><div data-cookie='1'>cookie banner</div></div>",
        "html.parser",
    )
    md = convert_to_markdown(soup.div, _cfg(strip_selectors=["[data-cookie]"]))
    assert "Body" in md
    assert "cookie banner" not in md


def test_preserve_classes_overrides_strip():
    soup = BeautifulSoup(
        "<div><p class='ad keep'>survives</p><p class='ad'>dies</p></div>",
        "html.parser",
    )
    md = convert_to_markdown(
        soup.div, _cfg(strip_classes=["ad"], preserve_classes=["keep"])
    )
    assert "survives" in md
    assert "dies" not in md


def test_heading_style_setext():
    soup = BeautifulSoup("<div><h1>Title</h1></div>", "html.parser")
    md = convert_to_markdown(soup.div, _cfg(heading_style="SETEXT"))
    # SETEXT renders h1 as underlined =
    assert "=" in md
    assert "Title" in md


def test_link_with_text_preserved():
    soup = BeautifulSoup(
        '<div><a href="https://example.com/x">click</a></div>', "html.parser"
    )
    md = convert_to_markdown(soup.div, _cfg())
    assert "[click](https://example.com/x)" in md
