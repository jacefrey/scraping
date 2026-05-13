"""PDF URL branch — saves <stem>.pdf, no MD generated (spec §5.9 v0.1)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from webpage_to_md import convert, ConvertResult


FIX = Path(__file__).parent / "fixtures"


def _pdf_result():
    return SimpleNamespace(
        requested_url="https://example.com/whitepaper.pdf",
        final_url="https://example.com/whitepaper.pdf",
        redirect_chain=[],
        started_at=datetime(2026, 5, 12, 10, 29, 59, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 30, 0, tzinfo=timezone.utc),
        content=(FIX / "sample.pdf").read_bytes(),
        content_type="application/pdf",
        content_type_source="url_suffix",
        encoding=None,
        content_length_bytes=0,
        content_hash_sha256="b1" * 32,
        http_status=200,
        fetch_method="http",
        error_category=None,
        headers={},
        etag=None,
        last_modified=None,
        not_modified=False,
        playwright_details=None,
    )


def test_pdf_url_saves_pdf_and_no_md(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _pdf_result()
        result = convert(
            "https://example.com/whitepaper.pdf",
            output_dir=tmp_path,
        )
    assert isinstance(result, ConvertResult)
    assert result.md_generated is False
    assert result.markdown_path is None
    assert result.pdf_path is not None
    assert result.pdf_path.is_file()
    assert result.pdf_path.suffix == ".pdf"
    # And NO MD or HTML files in the output dir
    siblings = {p.name for p in tmp_path.iterdir()}
    md_files = {n for n in siblings if n.endswith(".md")}
    html_files = {n for n in siblings if n.endswith(".html")}
    assert md_files == set()
    assert html_files == set()


def test_pdf_url_manifest_row_records_passthrough(tmp_path):
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _pdf_result()
        convert("https://example.com/whitepaper.pdf", output_dir=tmp_path)
    manifest = tmp_path / "manifest.jsonl"
    row = json.loads(manifest.read_text().splitlines()[0])
    assert row["status"] == "ok"
    assert row["content_type"] == "application/pdf"
    assert row["source_artifact"].endswith(".pdf")
    assert row["derived_artifact"] is None


def test_pdf_url_no_pdf_to_markdown_imported(tmp_path):
    """v0.1 invariant: pdf-to-markdown.process is NEVER called by webpage-to-md."""
    with patch("webpage_to_md.convert._fetch") as f:
        f.return_value = _pdf_result()
        result = convert("https://example.com/x.pdf", output_dir=tmp_path)
    assert result.md_generated is False
