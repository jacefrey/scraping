"""Stage 1 extraction tests (spec §5.6)."""
import pytest
from bs4 import BeautifulSoup
from webpage_to_md.extraction import select_content_node
from webpage_to_md.errors import ConvertConfigError


HTML = """
<html><head><title>X</title></head><body>
  <header><nav>nav</nav></header>
  <main>
    <article>
      <h1>Title</h1>
      <p class="body">Article body</p>
    </article>
  </main>
  <footer>footer</footer>
</body></html>
"""


def test_explicit_selector_wins():
    soup = BeautifulSoup(HTML, "html.parser")
    node = select_content_node(soup, selector=".body", strategy="selector_then_body")
    assert node is not None
    assert node.get_text(strip=True) == "Article body"


def test_explicit_selector_none_when_not_found():
    soup = BeautifulSoup(HTML, "html.parser")
    with pytest.raises(ConvertConfigError) as exc:
        select_content_node(soup, selector=".does-not-exist", strategy="selector_then_body")
    assert "selector" in str(exc.value).lower()


def test_body_fallback_uses_main():
    soup = BeautifulSoup(HTML, "html.parser")
    node = select_content_node(soup, selector=None, strategy="selector_then_body")
    assert node.name == "main"


def test_body_fallback_falls_through_to_article_when_no_main():
    html = "<html><body><article><p>x</p></article></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    node = select_content_node(soup, selector=None, strategy="selector_then_body")
    assert node.name == "article"


def test_body_fallback_falls_through_to_body_when_no_main_or_article():
    html = "<html><body><div><p>x</p></div></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    node = select_content_node(soup, selector=None, strategy="selector_then_body")
    assert node.name == "body"


def test_readability_strategy_raises_convert_config_error():
    """Spec §5.6: readability hook raises ConvertConfigError, NOT NotImplementedError."""
    soup = BeautifulSoup(HTML, "html.parser")
    with pytest.raises(ConvertConfigError) as exc:
        select_content_node(
            soup, selector=None, strategy="selector_then_readability_then_body"
        )
    assert "Readify" in str(exc.value) or "readability" in str(exc.value).lower()
    # Critical: not a NotImplementedError
    assert not isinstance(exc.value, NotImplementedError)


def test_readability_strategy_with_selector_uses_selector():
    """Even with readability strategy, an explicit selector takes precedence."""
    soup = BeautifulSoup(HTML, "html.parser")
    node = select_content_node(
        soup, selector=".body", strategy="selector_then_readability_then_body"
    )
    assert node.get_text(strip=True) == "Article body"
