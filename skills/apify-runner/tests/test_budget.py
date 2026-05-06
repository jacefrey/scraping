"""max_cost_usd / cost_buffer_percent tests (spec §7.7)."""
from unittest.mock import patch
import pytest
from apify_runner.runner import run
from apify_runner.errors import ApifyBudgetExceededError


def _baseline(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")


def _started(cost):
    return {"data": {"id": "run-1", "actId": "apify/x",
                     "defaultDatasetId": "ds-1", "status": "RUNNING",
                     "startedAt": "2026-05-04T10:00:00Z",
                     "finishedAt": None, "usage": {"totalUsd": cost}}}


def test_max_cost_exceeded_aborts_and_raises(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    poll_seq = [_started(0.50), _started(2.10)]  # 2.10 > 2.00 cap
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json", side_effect=poll_seq), \
         patch("apify_runner.runner._abort_run") as abort, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started(0.0)
        with pytest.raises(ApifyBudgetExceededError) as exc:
            run(actor="apify/x", input_data={}, max_cost_usd=2.00,
                timeout_s=60, poll_interval_s=1)
    abort.assert_called_once()
    assert exc.value.run_id == "run-1"
    assert exc.value.cost_usd == 2.10
    assert exc.value.max_cost_usd == 2.00


def test_cost_buffer_lowers_effective_cap(monkeypatch, tmp_path):
    """cap=2.00 with buffer=10% should trigger at 1.80, not 2.00."""
    _baseline(monkeypatch, tmp_path)
    poll_seq = [_started(0.50), _started(1.85)]  # 1.85 > 1.80 effective cap
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json", side_effect=poll_seq), \
         patch("apify_runner.runner._abort_run") as abort, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started(0.0)
        with pytest.raises(ApifyBudgetExceededError):
            run(actor="apify/x", input_data={}, max_cost_usd=2.00,
                cost_buffer_percent=10, timeout_s=60, poll_interval_s=1)
    abort.assert_called_once()


def test_under_budget_completes_normally(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    succeeded = {"data": {"id": "run-1", "actId": "apify/x",
                          "defaultDatasetId": "ds-1", "status": "SUCCEEDED",
                          "startedAt": "2026-05-04T10:00:00Z",
                          "finishedAt": "2026-05-04T10:00:05Z",
                          "usage": {"totalUsd": 0.30}}}
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json", return_value=succeeded), \
         patch("apify_runner.runner._paginated_dataset_items",
               return_value=iter([])), \
         patch("apify_runner.runner._abort_run") as abort, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started(0.0)
        result = run(actor="apify/x", input_data={}, max_cost_usd=1.00,
                     timeout_s=10, poll_interval_s=1)
    abort.assert_not_called()
    assert result.cost_usd == 0.30
