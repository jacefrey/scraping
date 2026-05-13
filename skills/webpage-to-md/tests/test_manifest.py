"""Manifest JSONL writer tests (spec §8.10)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from webpage_to_md.manifest import append_manifest_row


def _fake_result():
    return SimpleNamespace(
        requested_url="https://example.com/article",
        final_url="https://example.com/article",
        started_at=datetime(2026, 5, 12, 10, 29, 55, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 30, 0, tzinfo=timezone.utc),
        content_type="text/html",
        content_type_source="get_header",
        http_status=200,
        fetch_method="http",
        content_hash_sha256="a" * 64,
    )


def test_append_success_row(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p,
        status="ok",
        result=_fake_result(),
        source_artifact="x.html",
        derived_artifact="x.md",
        selector=None,
        extraction_strategy="selector_then_body",
        config_sha256="b" * 64,
        duration_ms=4250,
    )
    rows = [json.loads(l) for l in p.read_text().splitlines() if l]
    assert len(rows) == 1
    r = rows[0]
    assert r["manifest_schema_version"] == "1.0"
    assert r["requested_url"] == "https://example.com/article"
    assert r["final_url"] == "https://example.com/article"
    assert r["status"] == "ok"
    assert r["error_category"] is None
    assert r["error_message"] is None
    assert r["converter"] == "webpage-to-md"
    assert r["converter_version"] == "0.1.0"
    assert r["source_artifact"] == "x.html"
    assert r["derived_artifact"] == "x.md"
    assert r["duration_ms"] == 4250
    assert r["extraction_strategy"] == "selector_then_body"
    assert r["config_sha256"] == "b" * 64


def test_append_failure_row_with_null_fetch_fields(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p,
        status="failed",
        result=None,
        requested_url="https://nonexistent.example.com/article",
        error_category="network",
        error_message="DNS resolution failed",
        config_sha256="c" * 64,
        duration_ms=30000,
        started_at=datetime(2026, 5, 12, 10, 32, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 32, 30, tzinfo=timezone.utc),
        extraction_strategy="selector_then_body",
        selector=None,
    )
    rows = [json.loads(l) for l in p.read_text().splitlines() if l]
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "failed"
    assert r["requested_url"] == "https://nonexistent.example.com/article"
    assert r["final_url"] is None
    assert r["http_status"] is None
    assert r["error_category"] == "network"
    assert "DNS resolution failed" in r["error_message"]
    assert r["source_artifact"] is None
    assert r["derived_artifact"] is None


def test_append_two_rows_are_two_lines(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p,
        status="ok",
        result=_fake_result(),
        source_artifact="a.html",
        derived_artifact="a.md",
        selector=None,
        extraction_strategy="selector_then_body",
        config_sha256="x" * 64,
        duration_ms=10,
    )
    append_manifest_row(
        p,
        status="ok",
        result=_fake_result(),
        source_artifact="b.html",
        derived_artifact="b.md",
        selector=None,
        extraction_strategy="selector_then_body",
        config_sha256="x" * 64,
        duration_ms=20,
    )
    lines = [l for l in p.read_text().splitlines() if l]
    assert len(lines) == 2
    a, b = json.loads(lines[0]), json.loads(lines[1])
    assert a["source_artifact"] == "a.html"
    assert b["source_artifact"] == "b.html"


def test_error_message_truncated_to_500(tmp_path):
    p = tmp_path / "manifest.jsonl"
    append_manifest_row(
        p,
        status="failed",
        result=None,
        requested_url="https://x.com/",
        error_category="server_error",
        error_message="x" * 5000,
        config_sha256="y" * 64,
        duration_ms=10,
        started_at=datetime(2026, 5, 12, 0, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 0, 0, 1, tzinfo=timezone.utc),
        extraction_strategy="selector_then_body",
        selector=None,
    )
    r = json.loads(p.read_text().splitlines()[0])
    assert len(r["error_message"]) <= 500
