"""HTTP client wrapper tests (spec §7.8 — stdlib only)."""
from unittest.mock import patch, MagicMock
import json
import pytest
from apify_runner.client import _get_json, _post_json, _abort_run, ApifyHttpError


def _make_response(payload, status=200):
    r = MagicMock()
    r.status = status
    r.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = r
    cm.__exit__.return_value = False
    return cm


def test_get_json_returns_decoded_payload():
    cm = _make_response({"data": {"runId": "abc"}})
    with patch("apify_runner.client.urllib.request.urlopen", return_value=cm):
        out = _get_json("https://api.apify.com/v2/x", token="tok")
    assert out == {"data": {"runId": "abc"}}


def test_post_json_sends_body_and_decodes():
    cm = _make_response({"data": {"id": "run-1"}})
    with patch("apify_runner.client.urllib.request.urlopen",
               return_value=cm) as urlopen:
        out = _post_json(
            "https://api.apify.com/v2/acts/foo/runs",
            token="tok",
            body={"input": "x"},
        )
    assert out == {"data": {"id": "run-1"}}
    req = urlopen.call_args[0][0]
    assert req.method == "POST"
    assert req.headers["Authorization"] == "Bearer tok"


def test_get_json_on_404_raises_http_error():
    """urllib raises HTTPError for 4xx; client wraps as ApifyHttpError."""
    import urllib.error
    err = urllib.error.HTTPError(
        url="https://api.apify.com/v2/missing", code=404, msg="Not Found",
        hdrs=None,
        fp=MagicMock(read=MagicMock(return_value=b'{"error":"not found"}')),
    )
    err.read = lambda: b'{"error":"not found"}'
    with patch("apify_runner.client.urllib.request.urlopen", side_effect=err):
        with pytest.raises(ApifyHttpError) as exc:
            _get_json("https://api.apify.com/v2/missing", token="tok")
    assert exc.value.status == 404


def test_abort_run_calls_correct_endpoint():
    cm = _make_response({"data": {"status": "ABORTING"}})
    with patch("apify_runner.client.urllib.request.urlopen",
               return_value=cm) as urlopen:
        _abort_run("https://api.apify.com/v2", run_id="run-1", token="tok")
    req = urlopen.call_args[0][0]
    assert "actor-runs/run-1/abort" in req.full_url
    assert req.method == "POST"
