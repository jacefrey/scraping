"""URL → live-mode PDF (spec §6.2)."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from webpage_to_pdf import convert, ConvertResult


def _html_result(content=b"<html><body><p>hi</p></body></html>"):
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


def _mock_playwright_session(rendered_html_bytes: bytes, page_height_px: int = 2400):
    """Build a context-manager mock for sync_playwright()."""
    page = MagicMock()
    height_responses = iter([
        page_height_px,  # scrollHeight (lazy-load step 1)
        page_height_px,  # scrollHeight (lazy-load step 2, stable)
        page_height_px,  # scrollHeight (measure)
        100,             # clientHeight (don't fall through to body)
    ])

    def evaluate(script, *args, **kwargs):
        if "scrollHeight" in script or "clientHeight" in script:
            return next(height_responses, page_height_px)
        return None

    def pdf_side_effect(*args, **kwargs):
        path = kwargs.get("path") or (args[0] if args else None)
        if path:
            Path(path).write_bytes(b"%PDF-1.4 mock")

    page.evaluate.side_effect = evaluate
    page.pdf.side_effect = pdf_side_effect
    page.content.return_value = rendered_html_bytes.decode("utf-8")
    page.url = "https://example.com/a"

    browser = MagicMock()
    browser.new_page.return_value = page
    browser.new_context.return_value.new_page.return_value = page

    pw = MagicMock()
    pw.chromium.launch.return_value = browser

    cm = MagicMock()
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False
    return cm, page


def test_live_mode_writes_html_pdf_sidecar_and_returns_result(tmp_path):
    rendered = b"<html><body><p>RENDERED</p></body></html>"
    cm, page = _mock_playwright_session(rendered)

    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        result = convert(
            "https://example.com/a",
            output_dir=tmp_path,
        )

    assert isinstance(result, ConvertResult)
    assert result.render_mode == "live"
    assert result.live_double_fetch is True
    assert result.pdf_path.exists()
    assert result.source_html_path.exists()
    # persist_rendered_html defaults True for live mode
    assert result.rendered_html_path is not None
    assert result.rendered_html_path.exists()
    assert result.rendered_html_path.read_bytes() == rendered

    # Sidecar present alongside source HTML
    sidecar = result.source_html_path.with_suffix(".html.meta.json")
    assert sidecar.is_file()


def test_live_mode_playwright_navigates_to_original_url(tmp_path):
    cm, page = _mock_playwright_session(b"<html></html>")
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        convert("https://example.com/a", output_dir=tmp_path)
    # page.goto called with the original URL
    assert page.goto.called
    nav_target = page.goto.call_args[0][0]
    assert nav_target == "https://example.com/a"


def test_live_mode_records_manifest_live_double_fetch_true(tmp_path):
    cm, page = _mock_playwright_session(b"<html></html>")
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        convert("https://example.com/a", output_dir=tmp_path)
    row = json.loads((tmp_path / "manifest.jsonl").read_text().splitlines()[0])
    assert row["render_mode"] == "live"
    assert row["live_double_fetch"] is True
    assert row["render_html_sha256"] is not None
    assert row["rendered_html_artifact"]


def test_live_mode_flatten_sticky_auto_false_for_continuous(tmp_path):
    cm, page = _mock_playwright_session(b"<html></html>")
    with patch("webpage_to_pdf.convert._fetch") as f, \
         patch("webpage_to_pdf.convert.sync_playwright", return_value=cm):
        f.return_value = _html_result()
        convert("https://example.com/a", output_dir=tmp_path)
    # flatten_sticky=auto + page_format=continuous → no flatten call.
    scripts = [c.args[0] for c in page.evaluate.call_args_list if c.args]
    assert not any("originalPosition" in s for s in scripts)
