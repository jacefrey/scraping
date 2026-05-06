"""Playwright-path unit tests — sync_playwright is mocked."""
from unittest.mock import MagicMock, patch
import pytest
from webfetch.playwright_fetch import playwright_fetch
from webfetch.result import FetchError


def _baseline_cfg():
    from webfetch.config import load_config
    return load_config()


def _mock_pw_context(rendered_html="<html><body>rendered</body></html>",
                     final_url="https://example.com/", redirects=0):
    """Build a mock for the sync_playwright() context manager + page chain."""
    page = MagicMock()
    page.content.return_value = rendered_html
    page.url = final_url

    frame_nav_count = [0]

    def goto(url, **kw):
        frame_nav_count[0] += 1
        if redirects and frame_nav_count[0] <= redirects:
            page.url = f"{final_url}redirect-{frame_nav_count[0]}"
            return None
        page.url = final_url
        return None

    page.goto.side_effect = goto

    context = MagicMock()
    context.new_page.return_value = page

    browser = MagicMock()
    browser.new_context.return_value = context
    chromium = MagicMock()
    chromium.launch.return_value = browser

    pw = MagicMock()
    pw.chromium = chromium

    cm = MagicMock()
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False
    return cm, page, browser


def test_playwright_fetch_returns_rendered_html():
    cfg = _baseline_cfg()
    cm, page, browser = _mock_pw_context()
    with patch("webfetch.playwright_fetch.sync_playwright", return_value=cm):
        result = playwright_fetch("https://example.com/", cfg=cfg)
    assert result.fetch_method == "playwright"
    assert result.content == b"<html><body>rendered</body></html>"
    assert result.content_type == "text/html; charset=utf-8"
    assert result.content_type_source == "playwright_render"
    assert result.encoding == "utf-8"
    assert result.http_status == 200


def test_playwright_redirect_loop_raises():
    """When frame navigations exceed max_redirects, FetchError(redirect_loop) is raised."""
    cfg = _baseline_cfg()
    cfg["fetch"]["playwright"]["max_redirects"] = 1

    cm = MagicMock()
    pw = MagicMock()
    page = MagicMock()
    page.url = "https://example.com/loop"
    page.content.return_value = "<html></html>"

    def loop_goto(url, **kw):
        return None

    page.goto.side_effect = loop_goto

    context = MagicMock()
    context.new_page.return_value = page
    browser = MagicMock()
    browser.new_context.return_value = context
    chromium = MagicMock()
    chromium.launch.return_value = browser
    pw.chromium = chromium
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False

    # Force the frame-nav count to exceed max_redirects via the test seam.
    with patch("webfetch.playwright_fetch.sync_playwright", return_value=cm), \
         patch("webfetch.playwright_fetch._frame_navigation_count", return_value=2):
        with pytest.raises(FetchError) as exc:
            playwright_fetch("https://example.com/loop", cfg=cfg)
    assert exc.value.error_category == "redirect_loop"


def test_playwright_unavailable_when_browser_not_installed():
    """sync_playwright() raises with 'Executable doesn't exist' → playwright_unavailable."""
    cfg = _baseline_cfg()
    cm = MagicMock()
    cm.__enter__.side_effect = RuntimeError(
        "BrowserType.launch: Executable doesn't exist at "
        "/path/to/chromium-1234/chrome-mac/Chromium.app"
    )
    cm.__exit__.return_value = False
    with patch("webfetch.playwright_fetch.sync_playwright", return_value=cm):
        with pytest.raises(FetchError) as exc:
            playwright_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "playwright_unavailable"


def test_playwright_timeout_raises_timeout_category():
    """page.goto() raises PWTimeoutError → FetchError(timeout)."""
    from playwright.sync_api import TimeoutError as PWTimeoutError
    cfg = _baseline_cfg()
    cm, page, browser = _mock_pw_context()
    page.goto.side_effect = PWTimeoutError("Timeout 30000ms exceeded")
    with patch("webfetch.playwright_fetch.sync_playwright", return_value=cm):
        with pytest.raises(FetchError) as exc:
            playwright_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "timeout"


def test_playwright_no_redirect_returns_empty_chain():
    """When final_url == requested_url, redirect_chain is empty per spec §4.1."""
    cfg = _baseline_cfg()
    cm, page, browser = _mock_pw_context()
    with patch("webfetch.playwright_fetch.sync_playwright", return_value=cm):
        result = playwright_fetch("https://example.com/", cfg=cfg)
    assert result.redirect_chain == []
    assert result.final_url == "https://example.com/"
