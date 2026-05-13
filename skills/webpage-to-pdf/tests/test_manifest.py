"""Manifest tests for webpage-to-pdf (spec §8.10)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from webpage_to_pdf.manifest import append_manifest_row


def _result():
    return SimpleNamespace(
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        started_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 0, 5, tzinfo=timezone.utc),
        content_type="text/html",
        content_type_source="get_header",
        fetch_method="http",
        http_status=200,
        content_hash_sha256="a" * 64,
    )


def test_live_mode_row(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p, status="ok", result=_result(),
        source_artifact="x.html",
        derived_artifact="x.pdf",
        selector=None,
        config_sha256="c" * 64,
        duration_ms=12345,
        render_mode="live",
        page_format="continuous",
        flatten_sticky=False,
        hide_fixed=False,
        live_double_fetch=True,
        render_html_sha256="b" * 64,
        rendered_html_artifact="x.rendered.html",
    )
    row = json.loads(p.read_text().splitlines()[0])
    assert row["converter"] == "webpage-to-pdf"
    assert row["render_mode"] == "live"
    assert row["page_format"] == "continuous"
    assert row["live_double_fetch"] is True
    assert row["render_html_sha256"] == "b" * 64
    assert row["rendered_html_artifact"] == "x.rendered.html"
    assert row["flatten_sticky"] is False
    assert row["hide_fixed"] is False
    assert "extraction_strategy" not in row
    assert row["status"] == "ok"


def test_captured_html_row_no_rendered_html(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p, status="ok", result=_result(),
        source_artifact="x.html",
        derived_artifact="x.pdf",
        selector="article",
        config_sha256="c" * 64,
        duration_ms=10,
        render_mode="captured_html",
        page_format="Letter",
        flatten_sticky=True,
        hide_fixed=False,
        live_double_fetch=False,
        render_html_sha256=None,
        rendered_html_artifact=None,
    )
    row = json.loads(p.read_text().splitlines()[0])
    assert row["render_mode"] == "captured_html"
    assert row["live_double_fetch"] is False
    assert row["render_html_sha256"] is None
    assert row["rendered_html_artifact"] is None
    assert row["selector"] == "article"


def test_passthrough_row(tmp_path):
    p = tmp_path / "manifest.jsonl"
    pdf_result = SimpleNamespace(**dict(
        _result().__dict__,
        content_type="application/pdf",
    ))
    append_manifest_row(
        p, status="ok", result=pdf_result,
        source_artifact="x.pdf",
        derived_artifact=None,
        selector=None,
        config_sha256="c" * 64,
        duration_ms=10,
        render_mode=None,
        page_format=None,
        flatten_sticky=None,
        hide_fixed=None,
        live_double_fetch=None,
        render_html_sha256=None,
        rendered_html_artifact=None,
        passthrough=True,
    )
    row = json.loads(p.read_text().splitlines()[0])
    assert row["passthrough"] is True
    assert row["content_type"] == "application/pdf"


def test_failure_row(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p, status="failed", result=None,
        requested_url="https://example.com/oops",
        error_category="network",
        error_message="DNS failed",
        config_sha256="c" * 64,
        duration_ms=30000,
        started_at=datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 0, 30, tzinfo=timezone.utc),
        render_mode="live",
        page_format="continuous",
        flatten_sticky=False,
        hide_fixed=False,
    )
    row = json.loads(p.read_text().splitlines()[0])
    assert row["status"] == "failed"
    assert row["error_category"] == "network"
    assert row["http_status"] is None
