"""HTTP path tests — mocked requests transport (spec §4.1, §4.2)."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from requests.structures import CaseInsensitiveDict
from webfetch.http import http_fetch
from webfetch.result import FetchError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _mock_response(status=200, body=b"<html><body>hi</body></html>",
                   headers=None, url="https://example.com/"):
    r = MagicMock()
    r.status_code = status
    r.content = body
    r.headers = CaseInsensitiveDict(headers or {"Content-Type": "text/html; charset=utf-8"})
    r.url = url
    r.history = []
    r.encoding = "utf-8"
    return r


def test_http_fetch_static_html_returns_200():
    cfg = _baseline_cfg()
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = _mock_response()
        result = http_fetch("https://example.com/article", cfg=cfg)
    assert result.http_status == 200
    assert result.fetch_method == "http"
    assert result.content_type.startswith("text/html")
    assert result.content_type_source == "get_header"
    assert result.content_hash_sha256 is not None
    assert len(result.content_hash_sha256) == 64  # hex sha256
    assert result.error_category is None


def test_http_fetch_records_redirect_chain():
    cfg = _baseline_cfg()
    hop1 = MagicMock(url="https://example.com/", status_code=301)
    hop2 = MagicMock(url="https://example.com/v2", status_code=302)
    final = _mock_response(url="https://example.com/v2/article")
    final.history = [hop1, hop2]
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = final
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.requested_url == "https://example.com/"
    assert result.final_url == "https://example.com/v2/article"
    assert result.redirect_chain == [
        "https://example.com/",
        "https://example.com/v2",
    ]


def test_http_fetch_404_raises_not_found():
    cfg = _baseline_cfg()
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = _mock_response(status=404, body=b"not found")
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/missing", cfg=cfg)
    assert exc.value.error_category == "not_found"


def test_http_fetch_url_normalization_no_redirect_chain():
    """Server URL-normalizes without 3xx — final_url differs but no redirect occurred."""
    cfg = _baseline_cfg()
    final = _mock_response(url="https://example.com/article/")  # trailing slash added
    final.history = []  # no redirects
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = final
        result = http_fetch("https://example.com/article", cfg=cfg)
    assert result.requested_url == "https://example.com/article"
    assert result.final_url == "https://example.com/article/"
    assert result.redirect_chain == []  # empty — no 3xx redirect occurred


def _baseline_cfg():
    from webfetch.config import load_config
    return load_config()


import requests as _requests


def test_http_timeout_retries_then_succeeds():
    cfg = _baseline_cfg()
    cfg["fetch"]["http_timeout_retries"] = 2
    sequence = [
        _requests.exceptions.ReadTimeout("first"),
        _requests.exceptions.ReadTimeout("second"),
        _mock_response(),
    ]
    with patch("webfetch.http._do_get", side_effect=sequence), \
         patch("webfetch.http.time.sleep"):
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200


def test_http_timeout_exhausts_retries_then_raises():
    cfg = _baseline_cfg()
    cfg["fetch"]["http_timeout_retries"] = 1
    with patch("webfetch.http._do_get",
               side_effect=_requests.exceptions.ReadTimeout("hung")), \
         patch("webfetch.http.time.sleep"):
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "timeout"


def test_429_honors_retry_after():
    cfg = _baseline_cfg()
    cfg["fetch"]["politeness"]["respect_retry_after"] = True
    cfg["fetch"]["politeness"]["max_retry_after_s"] = 30
    seq = [
        _mock_response(status=429,
                       headers={"Retry-After": "5",
                                "Content-Type": "text/plain"},
                       body=b""),
        _mock_response(),
    ]
    with patch("webfetch.http._do_get", side_effect=seq) as do_get, \
         patch("webfetch.http.time.sleep") as sleep:
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200
    sleep.assert_any_call(5)
    assert do_get.call_count == 2


def test_network_retries_on_connection_error():
    cfg = _baseline_cfg()
    cfg["fetch"]["network_retries"] = 2
    seq = [
        _requests.exceptions.ConnectionError("dns fail 1"),
        _requests.exceptions.ConnectionError("dns fail 2"),
        _mock_response(),
    ]
    with patch("webfetch.http._do_get", side_effect=seq), \
         patch("webfetch.http.time.sleep"):
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200


def test_connect_timeout_uses_network_retries_not_timeout_retries():
    """ConnectTimeout (host down) must use network_retries, not http_timeout_retries."""
    cfg = _baseline_cfg()
    cfg["fetch"]["network_retries"] = 2
    cfg["fetch"]["http_timeout_retries"] = 0  # If ConnectTimeout were misrouted, this kills retry.
    sequence = [
        _requests.exceptions.ConnectTimeout("first"),
        _requests.exceptions.ConnectTimeout("second"),
        _mock_response(),
    ]
    with patch("webfetch.http._do_get", side_effect=sequence), \
         patch("webfetch.http.time.sleep"):
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200


def test_connect_timeout_exhausts_network_retries_raises_network():
    cfg = _baseline_cfg()
    cfg["fetch"]["network_retries"] = 1
    with patch("webfetch.http._do_get",
               side_effect=_requests.exceptions.ConnectTimeout("host down")), \
         patch("webfetch.http.time.sleep"):
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "network"  # NOT "timeout"


def test_500_retries_once_then_succeeds():
    cfg = _baseline_cfg()
    cfg["fetch"]["politeness"]["respect_retry_after"] = True
    seq = [
        _mock_response(status=500, body=b"oops"),
        _mock_response(),  # 200 on retry
    ]
    with patch("webfetch.http._do_get", side_effect=seq) as do_get, \
         patch("webfetch.http.time.sleep") as sleep:
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200
    assert do_get.call_count == 2
    sleep.assert_called_with(5)  # default 5 s when no Retry-After


def test_500_two_failures_raises_server_error():
    cfg = _baseline_cfg()
    cfg["fetch"]["politeness"]["respect_retry_after"] = True
    seq = [
        _mock_response(status=500, body=b"oops"),
        _mock_response(status=500, body=b"oops"),  # second 500 also
    ]
    with patch("webfetch.http._do_get", side_effect=seq), \
         patch("webfetch.http.time.sleep"):
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "server_error"


def test_503_honors_retry_after():
    cfg = _baseline_cfg()
    cfg["fetch"]["politeness"]["respect_retry_after"] = True
    cfg["fetch"]["politeness"]["max_retry_after_s"] = 30
    seq = [
        _mock_response(status=503,
                       headers={"Retry-After": "10",
                                "Content-Type": "text/plain"},
                       body=b"backoff"),
        _mock_response(),
    ]
    with patch("webfetch.http._do_get", side_effect=seq) as do_get, \
         patch("webfetch.http.time.sleep") as sleep:
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200
    sleep.assert_any_call(10)
    assert do_get.call_count == 2


def test_magic_byte_detects_pdf_via_streamed_peek():
    """URL has no .pdf suffix and no HEAD content-type, but body starts with %PDF.
    Skill should classify as PDF without issuing a second GET."""
    cfg = _baseline_cfg()
    pdf_bytes = b"%PDF-1.4\n%binary\n" + b"\x00" * 200
    fake = _mock_response(
        body=pdf_bytes,
        headers={"Content-Type": "application/octet-stream"},
        url="https://example.com/download/file",
    )
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        result = http_fetch("https://example.com/download/file", cfg=cfg)
    assert result.content_type == "application/pdf"
    assert result.content_type_source == "magic_bytes"
    assert do_get.call_count == 1


def test_magic_byte_html_body_routes_as_html():
    """Body does NOT start with %PDF — should be treated as HTML, no re-fetch."""
    cfg = _baseline_cfg()
    fake = _mock_response(
        body=b"<!DOCTYPE html><html><body>article</body></html>",
        headers={"Content-Type": "application/octet-stream"},
        url="https://example.com/x",
    )
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        result = http_fetch("https://example.com/x", cfg=cfg)
    assert result.content_type != "application/pdf"
    assert do_get.call_count == 1


def test_pdf_url_suffix_classified_without_peek():
    cfg = _baseline_cfg()
    fake = _mock_response(
        body=b"%PDF-1.4\n",
        headers={"Content-Type": "application/pdf"},
        url="https://example.com/file.pdf",
    )
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        result = http_fetch("https://example.com/file.pdf", cfg=cfg)
    # url_suffix wins over head per detect.py priority
    assert result.content_type == "application/pdf"
    assert result.content_type_source in ("url_suffix", "head")


def test_cloudflare_challenge_raises_bot_challenge():
    cfg = _baseline_cfg()
    challenge_html = (FIXTURES_DIR / "cloudflare-challenge.html").read_bytes()
    fake = _mock_response(
        body=challenge_html,
        headers={"Content-Type": "text/html"},
        status=200,
    )
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "bot_challenge"


def test_return_blocked_content_yields_partial():
    cfg = _baseline_cfg()
    cfg["fetch"]["return_blocked_content"] = True
    challenge_html = (FIXTURES_DIR / "cloudflare-challenge.html").read_bytes()
    fake = _mock_response(body=challenge_html, status=200)
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.error_category == "bot_challenge"
    assert result.content == challenge_html


def test_clean_page_no_challenge_flag():
    cfg = _baseline_cfg()
    clean_html = (FIXTURES_DIR / "static-blog.html").read_bytes()
    fake = _mock_response(body=clean_html, status=200)
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.error_category is None


def test_extra_challenge_markers_from_config():
    """Custom marker passed via config is detected end-to-end."""
    cfg = _baseline_cfg()
    cfg["fetch"]["detection"]["challenge_markers"] = ["Imperva-Incapsula-Block"]
    body = (b"<!DOCTYPE html><html><head><title>Page</title></head>"
            b"<body>Imperva-Incapsula-Block triggered</body></html>")
    fake = _mock_response(body=body, headers={"Content-Type": "text/html"}, status=200)
    with patch("webfetch.http._do_get") as do_get:
        do_get.return_value = fake
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "bot_challenge"


def test_head_pdf_short_circuits_via_classifier():
    """HEAD returns application/pdf — classifier should pick it up."""
    cfg = _baseline_cfg()
    cfg["fetch"]["use_head"] = True
    head_resp = MagicMock(
        status_code=200,
        headers=CaseInsensitiveDict({"Content-Type": "application/pdf"}),
        url="https://example.com/file",
    )
    get_resp = _mock_response(
        body=b"%PDF-1.4\n",
        headers={"Content-Type": "application/pdf"},
        url="https://example.com/file",
    )
    with patch("webfetch.http._do_head") as do_head, \
         patch("webfetch.http._do_get") as do_get:
        do_head.return_value = head_resp
        do_get.return_value = get_resp
        result = http_fetch("https://example.com/file", cfg=cfg)
    assert result.content_type == "application/pdf"
    # URL has no .pdf suffix; source should be "head" (HEAD wins over magic_bytes per detect.py priority)
    assert result.content_type_source in ("head", "magic_bytes")


def test_head_failure_does_not_block_get():
    cfg = _baseline_cfg()
    cfg["fetch"]["use_head"] = True
    with patch("webfetch.http._do_head",
               side_effect=_requests.exceptions.RequestException("HEAD blocked")), \
         patch("webfetch.http._do_get") as do_get:
        do_get.return_value = _mock_response()
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.http_status == 200


def test_head_disabled_via_config_skips_head_call():
    """When use_head=False, HEAD should not be attempted at all."""
    cfg = _baseline_cfg()
    cfg["fetch"]["use_head"] = False
    with patch("webfetch.http._do_head") as do_head, \
         patch("webfetch.http._do_get") as do_get:
        do_get.return_value = _mock_response()
        result = http_fetch("https://example.com/", cfg=cfg)
    do_head.assert_not_called()
    assert result.http_status == 200


# parse_safety caps (spec §4.3) -------------------------------------------------

def test_response_too_large_via_content_length():
    """Server-declared Content-Length above max_response_bytes → response_too_large.
    Best-effort gate: cooperative servers let us bail before reading the body."""
    cfg = _baseline_cfg()
    cfg["fetch"]["parse_safety"]["max_response_bytes"] = 1000
    fake = _mock_response(headers={
        "Content-Type": "text/html",
        "Content-Length": "100000000",
    })
    with patch("webfetch.http._do_get") as do_get, \
         patch("webfetch.http._do_head") as do_head:
        do_get.return_value = fake
        do_head.return_value = MagicMock(status_code=200, headers=CaseInsensitiveDict({}))
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "response_too_large"
    assert exc.value.context["content_length"] == 100000000
    assert exc.value.context["max_response_bytes"] == 1000


def test_decoded_body_too_large_when_no_content_length():
    """Body exceeds max_decoded_bytes with no Content-Length header to gate
    the read pre-emptively → decoded_body_too_large after buffering."""
    cfg = _baseline_cfg()
    cfg["fetch"]["parse_safety"]["max_decoded_bytes"] = 100
    big_body = b"<html>" + b"x" * 10_000 + b"</html>"
    fake = _mock_response(body=big_body, headers={"Content-Type": "text/html"})
    with patch("webfetch.http._do_get") as do_get, \
         patch("webfetch.http._do_head") as do_head:
        do_get.return_value = fake
        do_head.return_value = MagicMock(status_code=200, headers=CaseInsensitiveDict({}))
        with pytest.raises(FetchError) as exc:
            http_fetch("https://example.com/", cfg=cfg)
    assert exc.value.error_category == "decoded_body_too_large"
    assert exc.value.context["decoded_bytes"] == len(big_body)


def test_parse_safety_caps_pass_under_threshold():
    """Body under both caps → returns normally."""
    cfg = _baseline_cfg()
    cfg["fetch"]["parse_safety"]["max_response_bytes"] = 1_000_000
    cfg["fetch"]["parse_safety"]["max_decoded_bytes"] = 1_000_000
    body = b"<html><body>tiny</body></html>"
    fake = _mock_response(body=body, headers={
        "Content-Type": "text/html",
        "Content-Length": str(len(body)),
    })
    with patch("webfetch.http._do_get") as do_get, \
         patch("webfetch.http._do_head") as do_head:
        do_get.return_value = fake
        do_head.return_value = MagicMock(status_code=200, headers=CaseInsensitiveDict({}))
        result = http_fetch("https://example.com/", cfg=cfg)
    assert result.error_category is None
    assert result.content == body
