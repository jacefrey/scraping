"""Test the FetchResult / FetchError types."""
from datetime import datetime, timezone
from webfetch.result import FetchResult, FetchError


def test_fetch_result_required_fields():
    started = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
    completed = datetime(2026, 5, 4, 10, 0, 1, tzinfo=timezone.utc)
    r = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        redirect_chain=[],
        started_at=started,
        completed_at=completed,
        content=b"<html></html>",
        content_type="text/html",
        content_type_source="get_header",
        encoding="utf-8",
        content_length_bytes=13,
        content_hash_sha256="abc",
        http_status=200,
        fetch_method="http",
        error_category=None,
        headers={},
    )
    assert r.requested_url == "https://example.com"
    assert r.duration_ms == 1000.0  # derived
    assert r.fetched_at == completed  # alias
    assert r.not_modified is False  # default
    assert r.etag is None
    assert r.last_modified is None
    assert r.playwright_details is None


def test_fetch_error_has_category():
    err = FetchError("not_found", "404 on https://example.com")
    assert err.error_category == "not_found"
    assert "404" in str(err)


def test_fetch_error_with_context_kwargs():
    err = FetchError(
        "timeout",
        "HTTP timeout on https://example.com",
        http_status=408,
        url="https://example.com",
        attempt=2,
    )
    assert err.error_category == "timeout"
    assert err.context == {
        "http_status": 408,
        "url": "https://example.com",
        "attempt": 2,
    }
