"""Content-type detection tests (spec §4.2 step 3)."""
from webfetch.detect import classify_content_type


def test_url_ends_with_pdf():
    ct, src = classify_content_type(
        url="https://example.com/whitepaper.pdf",
        head_content_type=None,
        peek_bytes=None,
    )
    assert ct == "application/pdf"
    assert src == "url_suffix"


def test_head_returns_pdf():
    ct, src = classify_content_type(
        url="https://example.com/download/file",
        head_content_type="application/pdf",
        peek_bytes=None,
    )
    assert ct == "application/pdf"
    assert src == "head"


def test_magic_bytes_pdf():
    ct, src = classify_content_type(
        url="https://example.com/x",
        head_content_type=None,
        peek_bytes=b"%PDF-1.7\n%\xe2\xe3\xcf\xd3" + b"\x00" * 100,
    )
    assert ct == "application/pdf"
    assert src == "magic_bytes"


def test_magic_bytes_not_pdf():
    ct, src = classify_content_type(
        url="https://example.com/x",
        head_content_type=None,
        peek_bytes=b"<!DOCTYPE html>\n<html>" + b" " * 100,
    )
    # Caller should treat as HTML / route to step 5
    assert ct is None
    assert src is None


def test_get_header_text_html():
    ct, src = classify_content_type(
        url="https://example.com/article",
        head_content_type=None,
        peek_bytes=None,
        get_content_type="text/html; charset=utf-8",
    )
    assert ct == "text/html"
    assert src == "get_header"


def test_url_uppercase_pdf_extension():
    """`.PDF` (uppercase) is detected via case-insensitive path comparison."""
    ct, src = classify_content_type(
        url="https://example.com/UPPERCASE.PDF",
        head_content_type=None,
        peek_bytes=None,
    )
    assert ct == "application/pdf"
    assert src == "url_suffix"


def test_url_pdf_with_query_string():
    """`.pdf?v=3` — query string doesn't break suffix detection."""
    ct, src = classify_content_type(
        url="https://example.com/whitepaper.pdf?v=3&utm=foo",
        head_content_type=None,
        peek_bytes=None,
    )
    assert ct == "application/pdf"
    assert src == "url_suffix"


from pathlib import Path
from webfetch.detect import is_thin_shell, is_challenge_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_thin_shell_detects_next_app():
    html = (FIXTURES / "thin-shell.html").read_bytes()
    assert is_thin_shell(html, http_thin_threshold_bytes=2048) is True


def test_thin_shell_passes_static_article():
    html = (FIXTURES / "static-blog.html").read_bytes()
    assert is_thin_shell(html, http_thin_threshold_bytes=2048) is False


def test_challenge_detection_cloudflare():
    html = (FIXTURES / "cloudflare-challenge.html").read_bytes()
    title_match, marker = is_challenge_page(html, http_status=403, extra_markers=[])
    assert title_match is True or marker is not None


def test_challenge_detection_clean_page():
    html = (FIXTURES / "static-blog.html").read_bytes()
    title_match, marker = is_challenge_page(html, http_status=200, extra_markers=[])
    assert title_match is False
    assert marker is None
