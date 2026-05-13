"""Sidecar JSON tests (spec §5.3 — shared shape across webpage-to-md/pdf)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from webpage_to_pdf.sidecar import write_meta_sidecar, read_meta_sidecar


def _result():
    return SimpleNamespace(
        requested_url="https://example.com/a",
        final_url="https://example.com/a",
        completed_at=datetime(2026, 5, 12, 10, 30, 0, tzinfo=timezone.utc),
        fetch_method="http",
        http_status=200,
        content_type_source="get_header",
        etag=None,
        last_modified=None,
        redirect_chain=[],
        content_hash_sha256="a" * 64,
    )


def test_round_trip(tmp_path):
    p = tmp_path / "x.html.meta.json"
    write_meta_sidecar(p, result=_result(), web_fetch_version="0.1.0")
    data = read_meta_sidecar(p)
    assert data["url"] == "https://example.com/a"
    assert data["fetched_at"] == "2026-05-12T10:30:00+00:00"
    assert data["fetch_method"] == "http"
    assert data["web-fetch_version"] == "0.1.0"


def test_read_returns_none_when_absent(tmp_path):
    assert read_meta_sidecar(tmp_path / "missing.html.meta.json") is None
