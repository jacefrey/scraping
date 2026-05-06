"""Live-URL integration tests — gated; not run in default suite (spec §8.8).

Run via: pytest -m integration

Single live-fetch smoke test against example.com — a stable, well-known
public test target that won't go away or rate-limit us. If this fails:
  - Network is offline (run again later)
  - example.com changed its body (update assertion below)
  - Our HTTP path broke (real bug; debug via verbose pytest -v -s)
"""
import pytest
from webfetch import fetch


@pytest.mark.integration
def test_live_fetch_example_com():
    """Smoke: fetch example.com over HTTP, confirm 200 + HTML + expected body."""
    result = fetch("https://example.com/")
    assert result.http_status == 200
    assert result.fetch_method in ("http", "playwright")
    assert (result.content_type or "").lower().startswith("text/html")
    assert b"Example Domain" in result.content
    assert result.content_hash_sha256 is not None
    assert len(result.content_hash_sha256) == 64
    assert result.error_category is None
