"""URL normalization tests — base href priority + srcset (spec §5.7)."""
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from webpage_to_md.provenance import normalize_relative_urls, resolve_base
from webpage_to_md.errors import ConvertError

FIX = Path(__file__).parent / "fixtures"


def test_base_href_wins_over_final_url():
    soup = BeautifulSoup((FIX / "base-href.html").read_bytes(), "html.parser")
    base = resolve_base(soup, final_url="https://example.com/orig/page")
    assert base == "https://cdn.example.com/v2/"


def test_final_url_used_when_no_base_tag():
    soup = BeautifulSoup((FIX / "srcset.html").read_bytes(), "html.parser")
    base = resolve_base(soup, final_url="https://example.com/article/")
    assert base == "https://example.com/article/"


def test_resolve_base_raises_when_both_missing():
    soup = BeautifulSoup((FIX / "srcset.html").read_bytes(), "html.parser")
    with pytest.raises(ConvertError):
        resolve_base(soup, final_url=None)


def test_anchors_normalized_against_base_href():
    soup = BeautifulSoup((FIX / "base-href.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article")
    a = soup.find("a")
    assert a["href"] == "https://cdn.example.com/v2/article/x"


def test_img_src_normalized():
    soup = BeautifulSoup((FIX / "base-href.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article")
    img = soup.find("img")
    assert img["src"] == "https://cdn.example.com/v2/images/a.png"


def test_img_srcset_rewritten_per_url():
    soup = BeautifulSoup((FIX / "base-href.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article")
    img = soup.find("img")
    assert "https://cdn.example.com/v2/images/a.png 1x" in img["srcset"]
    assert "https://cdn.example.com/v2/images/a@2x.png 2x" in img["srcset"]


def test_source_srcset_rewritten():
    soup = BeautifulSoup((FIX / "srcset.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article/")
    src_el = soup.find("source")
    assert "https://example.com/article/images/big.jpg 2x" in src_el["srcset"]
    assert "https://example.com/article/images/small.jpg 1x" in src_el["srcset"]


def test_iframe_src_rewritten():
    soup = BeautifulSoup((FIX / "srcset.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article/")
    iframe = soup.find("iframe")
    assert iframe["src"] == "https://example.com/article/embed/x"


def test_data_url_in_srcset_passes_through():
    soup = BeautifulSoup((FIX / "srcset.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article/")
    img = soup.find("img")
    # The data: entry must remain intact (commas inside base64 are not split).
    assert "data:image/png;base64,iVBORw0K" in img["srcset"]


def test_anchor_relative_climbs_resolved():
    soup = BeautifulSoup((FIX / "srcset.html").read_bytes(), "html.parser")
    soup = normalize_relative_urls(soup, base_url="https://example.com/article/")
    a = soup.find("a")
    assert a["href"] == "https://example.com/about"
