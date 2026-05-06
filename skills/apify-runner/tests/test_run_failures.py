"""run() failure-path tests (spec §7.4, §9.5)."""
import json
from unittest.mock import patch
import pytest
from apify_runner.runner import run
from apify_runner.errors import (
    ApifyRunFailedError, ApifyTimeoutError, ApifyActorNotFoundError,
)


def _started_payload(status="READY", cost=0.0):
    return {"data": {
        "id": "run-1", "actId": "apify/x", "defaultDatasetId": "ds-1",
        "status": status, "startedAt": "2026-05-04T10:00:00Z",
        "finishedAt": None,
        "usage": {"totalUsd": cost},
    }}


def _terminal_payload(status, cost):
    return {"data": {
        "id": "run-1", "actId": "apify/x", "defaultDatasetId": "ds-1",
        "status": status, "startedAt": "2026-05-04T10:00:00Z",
        "finishedAt": "2026-05-04T10:00:10Z",
        "usage": {"totalUsd": cost},
    }}


def _baseline(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")


def test_failed_run_raises_run_failed_with_metadata(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started_payload()
        get_json.return_value = _terminal_payload("FAILED", 0.13)
        with pytest.raises(ApifyRunFailedError) as exc:
            run(actor="apify/x", input_data={}, timeout_s=10, poll_interval_s=1)
    assert exc.value.run_id == "run-1"
    assert exc.value.status == "FAILED"
    assert exc.value.cost_usd_at_failure == 0.13
    assert exc.value.dataset_id == "ds-1"


def test_timeout_no_abort_carries_run_id(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._abort_run") as abort, \
         patch("apify_runner.runner.time.sleep"), \
         patch("apify_runner.runner.time.monotonic", side_effect=[0.0, 999.0, 999.0]):
        post.return_value = _started_payload(status="RUNNING", cost=0.10)
        get_json.return_value = _started_payload(status="RUNNING", cost=0.10)
        with pytest.raises(ApifyTimeoutError) as exc:
            run(actor="apify/x", input_data={}, timeout_s=5,
                poll_interval_s=1, abort_on_timeout=False)
    abort.assert_not_called()
    assert exc.value.run_id == "run-1"
    assert exc.value.status_at_timeout == "RUNNING"
    assert exc.value.aborted is False


def test_timeout_with_abort_calls_abort(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._abort_run") as abort, \
         patch("apify_runner.runner.time.sleep"), \
         patch("apify_runner.runner.time.monotonic", side_effect=[0.0, 999.0, 999.0]):
        post.return_value = _started_payload(status="RUNNING", cost=0.10)
        get_json.return_value = _started_payload(status="RUNNING", cost=0.10)
        with pytest.raises(ApifyTimeoutError) as exc:
            run(actor="apify/x", input_data={}, timeout_s=5,
                poll_interval_s=1, abort_on_timeout=True)
    abort.assert_called_once()
    assert exc.value.aborted is True


def test_zero_items_run_is_succeeded(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items") as paginate, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started_payload()
        get_json.return_value = _terminal_payload("SUCCEEDED", 0.02)
        paginate.return_value = iter([])
        result = run(actor="apify/x", input_data={}, timeout_s=10,
                     poll_interval_s=1)
    assert result.status == "SUCCEEDED"
    assert result.item_count == 0
    assert result.items == []


def test_actor_not_found_raises(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    from apify_runner.client import ApifyHttpError
    with patch("apify_runner.runner._post_json",
               side_effect=ApifyHttpError("404", status=404)):
        with pytest.raises(ApifyActorNotFoundError):
            run(actor="apify/missing", input_data={}, timeout_s=10,
                poll_interval_s=1)
