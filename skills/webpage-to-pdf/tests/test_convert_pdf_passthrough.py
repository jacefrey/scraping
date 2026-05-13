"""PDF passthrough (URL + local) (spec §6.2)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from webpage_to_pdf import convert, ConvertResult


FIX = Path(__file__).parent / "fixtures"


def _pdf_url_result():
    body = (FIX / "sample.pdf").read_bytes()
    return SimpleNamespace(
        requested_url="https://example.com/whitepaper.pdf",
        final_url="https://example.com/whitepaper.pdf",
        redirect_chain=[],
        started_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 0, 1, tzinfo=timezone.utc),
        content=body,
        content_type="application/pdf",
        content_type_source="url_suffix",
        encoding=None,
        content_length_bytes=len(body),
        content_hash_sha256=hashlib.sha256(body).hexdigest(),
        http_status=200,
        fetch_method="http",
        error_category=None,
        headers={},
        etag=None,
        last_modified=None,
        not_modified=False,
        playwright_details=None,
    )


def test_pdf_url_passthrough_copies_bytes_no_render(tmp_path):
    """No Playwright launch when content is PDF (spec §6.2)."""
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright") as pw:
        f.return_value = _pdf_url_result()
        result = convert(
            "https://example.com/whitepaper.pdf",
            output_dir=tmp_path,
        )
    assert isinstance(result, ConvertResult)
    assert result.passthrough is True
    assert result.render_mode is None
    assert result.source_html_path is None
    assert result.rendered_html_path is None
    assert result.pdf_path.is_file()
    assert result.pdf_path.suffix == ".pdf"
    assert result.pdf_path.read_bytes() == _pdf_url_result().content
    # Playwright must NOT have been invoked
    pw.assert_not_called()


def test_pdf_url_passthrough_manifest_row(tmp_path):
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright"):
        f.return_value = _pdf_url_result()
        convert("https://example.com/whitepaper.pdf", output_dir=tmp_path)
    row = json.loads((tmp_path / "manifest.jsonl").read_text().splitlines()[0])
    assert row["passthrough"] is True
    assert row["content_type"] == "application/pdf"
    assert row["render_mode"] is None
    assert row["source_artifact"].endswith(".pdf")


def test_local_pdf_passthrough_copies_bytes_no_render(tmp_path):
    """Local Path('x.pdf') triggers passthrough without Playwright."""
    src = tmp_path / "input.pdf"
    src.write_bytes((FIX / "sample.pdf").read_bytes())
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright") as pw:
        result = convert(src, output_dir=out_dir)
        f.assert_not_called()
    assert result.passthrough is True
    assert result.pdf_path.read_bytes() == src.read_bytes()
    pw.assert_not_called()
