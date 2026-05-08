"""Public fetch() entry point — mocks both http and playwright paths."""
from unittest.mock import patch
from datetime import datetime, timezone
import pytest
from webfetch import fetch, FetchError, FetchResult


def _baseline_fetch_cfg(domain_overrides=None):
    from webfetch.config import load_config
    cfg = load_config()
    if domain_overrides is not None:
        cfg["fetch"]["domain_overrides"] = domain_overrides
    return cfg


def _ok_http_result(method="http", content=b"<html><body>ok</body></html>"):
    started = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
    return FetchResult(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        redirect_chain=[],
        started_at=started,
        completed_at=started,
        content=content,
        content_type="text/html",
        content_type_source="get_header",
        encoding="utf-8",
        content_length_bytes=len(content),
        content_hash_sha256="x" * 64,
        http_status=200,
        fetch_method=method,
        error_category=None,
        headers={},
    )


@pytest.fixture(autouse=True)
def _reset_global_politeness():
    """Reset the module-level HostPoliteness between tests."""
    import webfetch
    webfetch._GLOBAL_POLITENESS = None
    yield
    webfetch._GLOBAL_POLITENESS = None


def test_fetch_method_http_uses_http_path():
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        hf.return_value = _ok_http_result()
        result = fetch("https://example.com/", fetch_method="http")
    hf.assert_called_once()
    pf.assert_not_called()
    assert result.fetch_method == "http"


def test_fetch_method_playwright_skips_heuristic():
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        pf.return_value = _ok_http_result(method="playwright")
        result = fetch("https://example.com/", fetch_method="playwright")
    pf.assert_called_once()
    hf.assert_not_called()
    assert result.fetch_method == "playwright"


def test_explicit_method_beats_domain_override():
    """Spec: explicit fetch_method != 'auto' wins over per-domain override."""
    cfg = _baseline_fetch_cfg(domain_overrides=[
        {"host": "example.com", "fetch_method": "playwright"}
    ])
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        hf.return_value = _ok_http_result()
        result = fetch("https://example.com/", fetch_method="http", cfg=cfg)
    hf.assert_called_once()
    pf.assert_not_called()


def test_auto_uses_domain_override():
    cfg = _baseline_fetch_cfg(domain_overrides=[
        {"host": "example.com", "fetch_method": "playwright"}
    ])
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        pf.return_value = _ok_http_result(method="playwright")
        result = fetch("https://example.com/", cfg=cfg)
    pf.assert_called_once()
    assert result.fetch_method == "playwright"


def test_auto_thin_shell_falls_back_to_playwright():
    """When auto-mode HTTP returns a thin shell, fallback to Playwright."""
    cfg = _baseline_fetch_cfg()
    thin_html = (
        b"<!DOCTYPE html><html><body><div id=\"__next\"></div>"
        b"<script id=\"__NEXT_DATA__\" type=\"application/json\">{}</script>"
        b"</body></html>"
    )
    http_thin = _ok_http_result(content=thin_html)
    pw_full = _ok_http_result(method="playwright")
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        hf.return_value = http_thin
        pf.return_value = pw_full
        result = fetch("https://example.com/", cfg=cfg)
    assert result.fetch_method == "playwright"


def test_auto_substantial_html_no_playwright_fallback():
    """Auto-mode: real HTML body keeps result, no fallback."""
    cfg = _baseline_fetch_cfg()
    full_html = b"<html><body>" + b"<p>real content here</p>" * 100 + b"</body></html>"
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        hf.return_value = _ok_http_result(content=full_html)
        result = fetch("https://example.com/", cfg=cfg)
    hf.assert_called_once()
    pf.assert_not_called()
    assert result.fetch_method == "http"


def test_fetch_method_typo_raises_value_error():
    """Invalid fetch_method (e.g. typo "playright") must fail fast — no auth,
    no politeness sleep, no dispatch."""
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep") as sleep_mock:
        with pytest.raises(ValueError, match="fetch_method must be"):
            fetch("https://example.com/", fetch_method="playright")
    hf.assert_not_called()
    pf.assert_not_called()
    sleep_mock.assert_not_called()


def test_return_blocked_content_passes_to_dispatch():
    """return_blocked_content=True flows into the cfg passed to http_fetch
    WITHOUT mutating the caller's cfg dict."""
    cfg = _baseline_fetch_cfg()
    original_value = cfg["fetch"]["return_blocked_content"]
    with patch("webfetch.http_fetch") as hf, \
         patch("webfetch.playwright_fetch") as pf, \
         patch("webfetch.politeness.time.sleep"):
        hf.return_value = _ok_http_result()
        fetch("https://example.com/", return_blocked_content=True, cfg=cfg)
    # Caller's cfg unmutated.
    assert cfg["fetch"]["return_blocked_content"] is original_value
    # The cfg actually dispatched to http_fetch HAS the override applied.
    dispatched_cfg = hf.call_args.kwargs["cfg"]
    assert dispatched_cfg["fetch"]["return_blocked_content"] is True
