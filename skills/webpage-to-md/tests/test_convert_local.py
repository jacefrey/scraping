"""Local-input fast path (spec §5.3)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml
from webpage_to_md import convert, ConvertResult


FIX = Path(__file__).parent / "fixtures"


def _write_local_html(tmp_path: Path, name: str = "saved.html") -> Path:
    p = tmp_path / name
    p.write_bytes((FIX / "simple-blog.html").read_bytes())
    return p


def _write_sidecar(html_path: Path) -> None:
    sidecar = html_path.with_suffix(".html.meta.json")
    sidecar.write_text(json.dumps({
        "url": "https://blog.example.com/bread",
        "final_url": "https://blog.example.com/bread",
        "fetched_at": "2026-05-10T10:30:00+00:00",
        "fetch_method": "http",
        "http_status": 200,
        "content_type_source": "get_header",
        "etag": None,
        "last_modified": None,
        "redirect_chain": [],
        "source_sha256": "a1" * 32,
        "web-fetch_version": "0.1.0",
    }))


def test_local_path_no_network_call(tmp_path):
    html = _write_local_html(tmp_path)
    _write_sidecar(html)

    fetch_called = []

    def boom(url):
        fetch_called.append(url)
        raise AssertionError("network must not be called for local input")

    with patch("webpage_to_md.convert._fetch", side_effect=boom):
        result = convert(html, output_dir=tmp_path)
    assert fetch_called == []
    assert isinstance(result, ConvertResult)
    assert result.md_generated is True
    assert result.markdown_path.is_file()


def test_local_path_uses_sidecar_provenance(tmp_path):
    html = _write_local_html(tmp_path)
    _write_sidecar(html)

    with patch("webpage_to_md.convert._fetch") as f:
        result = convert(html, output_dir=tmp_path)
        f.assert_not_called()

    md = result.markdown_path.read_text()
    end = md.index("\n---\n", 4)
    frontmatter = yaml.safe_load(md[4:end])
    assert frontmatter["url"] == "https://blog.example.com/bread"
    assert frontmatter["final_url"] == "https://blog.example.com/bread"
    assert frontmatter["original_fetched_at"] == "2026-05-10T10:30:00+00:00"
    assert "re_converted_at" in frontmatter


def test_local_path_falls_back_to_canonical_when_no_sidecar(tmp_path):
    html = _write_local_html(tmp_path)
    # NO sidecar written

    with patch("webpage_to_md.convert._fetch") as f:
        result = convert(html, output_dir=tmp_path)
        f.assert_not_called()

    md = result.markdown_path.read_text()
    end = md.index("\n---\n", 4)
    frontmatter = yaml.safe_load(md[4:end])
    # simple-blog.html has <link rel="canonical" href="https://blog.example.com/bread">
    assert frontmatter["url"] == "https://blog.example.com/bread"
    assert "original_fetched_at" not in frontmatter
    assert "re_converted_at" in frontmatter


def test_local_path_no_sidecar_no_canonical_uses_file_path(tmp_path):
    # Write HTML with no canonical link
    html = tmp_path / "raw.html"
    html.write_bytes(b"<html><head><title>x</title></head><body><p>hi</p></body></html>")

    with patch("webpage_to_md.convert._fetch") as f:
        result = convert(html, output_dir=tmp_path)
        f.assert_not_called()

    md = result.markdown_path.read_text()
    end = md.index("\n---\n", 4)
    frontmatter = yaml.safe_load(md[4:end])
    # url falls back to the local path string per §5.3
    assert str(html) in frontmatter["url"] or frontmatter["url"].endswith("raw.html")


def test_file_url_form_routes_like_path(tmp_path):
    html = _write_local_html(tmp_path)
    _write_sidecar(html)
    with patch("webpage_to_md.convert._fetch") as f:
        result = convert(f"file://{html}", output_dir=tmp_path)
        f.assert_not_called()
    assert result.md_generated is True


def test_local_manifest_row_records_re_conversion(tmp_path):
    html = _write_local_html(tmp_path)
    _write_sidecar(html)
    with patch("webpage_to_md.convert._fetch"):
        convert(html, output_dir=tmp_path)
    manifest = tmp_path / "manifest.jsonl"
    row = json.loads(manifest.read_text().splitlines()[0])
    assert row["status"] == "ok"
    assert row["fetch_method"] is None or row["fetch_method"] == "local"
    assert row["source_artifact"]  # whatever the convert path used
