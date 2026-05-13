"""URL → captured_html PDF (spec §6.2)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from webpage_to_pdf import convert, ConvertResult


def _html_result():
    content = b"<html><head><title>x</title></head><body><a href='/about'>about</a></body></html>"
    return SimpleNamespace(
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        redirect_chain=[],
        started_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 0, 5, tzinfo=timezone.utc),
        content=content,
        content_type="text/html; charset=utf-8",
        content_type_source="get_header",
        encoding="utf-8",
        content_length_bytes=len(content),
        content_hash_sha256=hashlib.sha256(content).hexdigest(),
        http_status=200,
        fetch_method="http",
        error_category=None,
        headers={},
        etag=None,
        last_modified=None,
        not_modified=False,
        playwright_details=None,
    )


def _mock_pw():
    page = MagicMock()
    # Return finite scrollHeight responses so the lazy-load loop terminates
    page.evaluate.side_effect = lambda *a, **k: 1000
    page.content.return_value = "<html></html>"

    # Make page.pdf write a dummy file
    def _pdf_write(path=None, **kwargs):
        if path:
            Path(path).write_bytes(b"%PDF-1.4 dummy")
    page.pdf.side_effect = _pdf_write

    browser = MagicMock()
    browser.new_page.return_value = page
    browser.new_context.return_value.new_page.return_value = page
    pw = MagicMock()
    pw.chromium.launch.return_value = browser
    cm = MagicMock()
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False
    return cm, page


def test_captured_html_navigates_to_file_url(tmp_path):
    cm, page = _mock_pw()
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        convert("https://example.com/a", output_dir=tmp_path,
                render_mode="captured_html")
    nav_target = page.goto.call_args[0][0]
    assert nav_target.startswith("file://")


def test_captured_html_injects_base_href(tmp_path):
    """Working HTML on disk has <base href> injected; persisted <stem>.html must NOT."""
    cm, page = _mock_pw()
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        convert("https://example.com/a", output_dir=tmp_path,
                render_mode="captured_html")
    # Find the persisted source HTML (not .rendered)
    persisted = next(p for p in tmp_path.iterdir()
                     if p.suffix == ".html" and ".rendered" not in p.name and ".meta" not in p.name)
    persisted_bytes = persisted.read_bytes()
    assert b"<base href=" not in persisted_bytes


def test_captured_html_records_live_double_fetch_false(tmp_path):
    cm, page = _mock_pw()
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        result = convert("https://example.com/a", output_dir=tmp_path,
                         render_mode="captured_html")
    assert result.render_mode == "captured_html"
    assert result.live_double_fetch is False
    assert result.rendered_html_path is None
    row = json.loads((tmp_path / "manifest.jsonl").read_text().splitlines()[0])
    assert row["render_mode"] == "captured_html"
    assert row["live_double_fetch"] is False
    assert row["rendered_html_artifact"] is None
