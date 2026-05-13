"""Public convert() HTML-URL path (spec §5.2)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import pytest
import yaml
from webpage_to_md import convert, ConvertResult


FIX = Path(__file__).parent / "fixtures"


def _ok_html_result(content: bytes | None = None,
                    final_url: str = "https://blog.example.com/bread"):
    return SimpleNamespace(
        requested_url=final_url,
        final_url=final_url,
        redirect_chain=[],
        started_at=datetime(2026, 5, 12, 10, 29, 59, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 30, 0, tzinfo=timezone.utc),
        content=content if content is not None else (FIX / "simple-blog.html").read_bytes(),
        content_type="text/html; charset=utf-8",
        content_type_source="get_header",
        encoding="utf-8",
        content_length_bytes=0,
        content_hash_sha256="a1" * 32,
        http_status=200,
        fetch_method="http",
        error_category=None,
        headers={},
        etag=None,
        last_modified=None,
        not_modified=False,
        playwright_details=None,
    )


def test_html_url_writes_html_md_meta_and_returns_result(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _ok_html_result()
        result = convert(
            source="https://blog.example.com/bread",
            output_dir=tmp_path,
        )

    assert isinstance(result, ConvertResult)
    assert result.md_generated is True
    assert result.markdown_path.exists()
    assert result.markdown_path.suffix == ".md"
    assert result.source_path.exists()
    assert result.source_path.suffix == ".html"
    # Sidecar (§5.3)
    sidecar = result.source_path.with_suffix(".html.meta.json")
    assert sidecar.is_file()


def test_html_url_md_contains_frontmatter_and_body(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _ok_html_result()
        result = convert("https://blog.example.com/bread", output_dir=tmp_path)

    md = result.markdown_path.read_text()
    assert md.startswith("---\n")
    # Find the closing fence
    end = md.index("\n---\n", 4)
    frontmatter = yaml.safe_load(md[4:end])
    body = md[end + 5:]
    assert frontmatter["url"] == "https://blog.example.com/bread"
    assert frontmatter["canonical_url"] == "https://blog.example.com/bread"
    assert frontmatter["title"]
    assert "How to bake bread" in body
    # Absolute link (relative `/about` → final_url)
    assert "[about page](https://blog.example.com/about)" in body


def test_html_url_emit_frontmatter_false_omits_block(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _ok_html_result()
        result = convert(
            "https://blog.example.com/bread",
            output_dir=tmp_path,
            emit_frontmatter=False,
        )
    md = result.markdown_path.read_text()
    assert not md.startswith("---\n")
    assert "How to bake bread" in md


def test_html_url_manifest_row_appended(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _ok_html_result()
        convert("https://blog.example.com/bread", output_dir=tmp_path)
    manifest = tmp_path / "manifest.jsonl"
    assert manifest.exists()
    row = json.loads(manifest.read_text().splitlines()[0])
    assert row["status"] == "ok"
    assert row["http_status"] == 200
    assert row["source_artifact"].endswith(".html")
    assert row["derived_artifact"].endswith(".md")
    assert row["extraction_strategy"] == "selector_then_body"


def test_html_url_fetch_failure_records_failure_row(tmp_path):
    from webpage_to_md.errors import ConvertError
    from webfetch import FetchError as WFFetchError  # noqa: F401  (proves import)

    class StubFetchError(Exception):
        def __init__(self):
            super().__init__("DNS failed")
            self.error_category = "network"

    with patch("webpage_to_md.convert._fetch", side_effect=StubFetchError()):
        with pytest.raises(Exception):
            convert("https://nonexistent.example.com/", output_dir=tmp_path)

    manifest = tmp_path / "manifest.jsonl"
    assert manifest.exists()
    row = json.loads(manifest.read_text().splitlines()[0])
    assert row["status"] == "failed"
    assert row["error_category"] == "network"
    assert row["source_artifact"] is None


def test_html_url_explicit_selector_narrows_extraction(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _ok_html_result()
        result = convert(
            "https://blog.example.com/bread",
            output_dir=tmp_path,
            selector="article",
        )
    md = result.markdown_path.read_text()
    # When selector="article", the frontmatter should record it.
    end = md.index("\n---\n", 4)
    frontmatter = yaml.safe_load(md[4:end])
    assert frontmatter["selector"] == "article"
