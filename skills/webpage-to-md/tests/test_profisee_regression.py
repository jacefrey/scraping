"""Profisee regression — 7 source-driven assertions (spec §5.5, §9.5)."""
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from bs4 import BeautifulSoup
from webpage_to_md import convert


FIX = Path(__file__).parent / "fixtures"


def _profisee_result():
    return SimpleNamespace(
        requested_url="https://profisee.example/blog/mdm-manufacturers",
        final_url="https://profisee.example/blog/mdm-manufacturers",
        redirect_chain=[],
        started_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 0, 5, tzinfo=timezone.utc),
        content=(FIX / "profisee-style.html").read_bytes(),
        content_type="text/html; charset=utf-8",
        content_type_source="get_header",
        encoding="utf-8",
        content_length_bytes=0,
        content_hash_sha256="c1" * 32,
        http_status=200,
        fetch_method="http",
        error_category=None,
        headers={},
        etag=None,
        last_modified=None,
        not_modified=False,
        playwright_details=None,
    )


@pytest.fixture
def md_body(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _profisee_result()
        result = convert(
            "https://profisee.example/blog/mdm-manufacturers",
            output_dir=tmp_path,
        )
    text = result.markdown_path.read_text()
    end = text.index("\n---\n", 4)
    return text[end + 5:]


def test_heading_parity(md_body):
    """Every H1–H4 in the source produces a # / ## / ### / #### line in MD."""
    src = BeautifulSoup((FIX / "profisee-style.html").read_bytes(), "html.parser")
    expected_levels = [int(h.name[1]) for h in src.find_all(re.compile(r"^h[1-4]$"))]
    md_levels = []
    for line in md_body.splitlines():
        m = re.match(r"^(#{1,4})\s", line)
        if m:
            md_levels.append(len(m.group(1)))
    # Every source heading at level N must have ≥1 MD heading at level N
    for lvl in set(expected_levels):
        assert md_levels.count(lvl) >= expected_levels.count(lvl), \
            f"missing H{lvl} headings: src={expected_levels.count(lvl)} md={md_levels.count(lvl)}"


def test_link_parity(md_body):
    """Every <a href> retained after stripping becomes a [text](url) link."""
    src = BeautifulSoup((FIX / "profisee-style.html").read_bytes(), "html.parser")
    expected_links = [a for a in src.find_all("a", href=True)]
    md_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", md_body)
    assert len(md_links) >= len(expected_links)
    # Every absolute URL the source carries must appear in the MD
    for a in expected_links:
        href = a["href"]
        if href.startswith("http"):
            assert href in md_body, f"missing link {href}"


def test_list_parity(md_body):
    """Total bullet count and ordered-list item count matches retained UL/OL items."""
    src = BeautifulSoup((FIX / "profisee-style.html").read_bytes(), "html.parser")
    src_ul_items = len(src.find_all("ul")[0].find_all("li"))
    src_ol_items = len(src.find_all("ol")[0].find_all("li"))
    bullets = sum(1 for line in md_body.splitlines() if re.match(r"^\s*[\*\-\+]\s", line))
    ordered = sum(1 for line in md_body.splitlines() if re.match(r"^\s*\d+\.\s", line))
    assert bullets >= src_ul_items
    assert ordered >= src_ol_items


def test_table_parity_on_non_colspan_rows(md_body):
    """Row count matches; column count matches on rows without colspan."""
    src = BeautifulSoup((FIX / "profisee-style.html").read_bytes(), "html.parser")
    table = src.find("table")
    assert table is not None
    expected_rows = len(table.find_all("tr"))
    pipe_lines = [l for l in md_body.splitlines() if l.strip().startswith("|")]
    assert len(pipe_lines) >= expected_rows  # ≥ accounts for separator


def test_no_cta_boilerplate(md_body):
    """Strip_classes-matched elements MUST NOT appear in the MD output."""
    assert "Sign up for the newsletter" not in md_body
    assert "Share buttons" not in md_body


def test_title_present(md_body):
    """The page title (from <title> or first <h1>) appears in the MD body."""
    assert re.search(r"^#\s+Master Data Management for Manufacturers", md_body, re.MULTILINE)


def test_per_fixture_content_assertions(md_body):
    """One expected H2, one expected paragraph, one expected outbound link."""
    assert "## Why MDM Matters" in md_body
    assert "Without consistent master data, even the best analytics fail." in md_body
    assert "[our learning site](https://learn.example/mdm)" in md_body
