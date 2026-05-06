"""HTTP path tests — mocked requests transport (spec §4.1, §4.2)."""
from unittest.mock import patch, MagicMock
import pytest
from requests.structures import CaseInsensitiveDict
from webfetch.http import http_fetch
from webfetch.result import FetchError


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
