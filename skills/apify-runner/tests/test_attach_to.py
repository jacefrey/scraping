"""attach_to() resume entry-point tests (spec §7.1)."""
from unittest.mock import patch
import pytest
from apify_runner.runner import attach_to


def _baseline(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")


def _existing_run(status, cost):
    return {"data": {"id": "run-existing", "actId": "apify/heavy",
                     "defaultDatasetId": "ds-existing", "status": status,
                     "startedAt": "2026-05-04T09:00:00Z",
                     "finishedAt": ("2026-05-04T10:00:00Z"
                                    if status in ("SUCCEEDED", "FINISHED",
                                                  "FAILED", "ABORTED")
                                    else None),
                     "usage": {"totalUsd": cost}}}


def test_attach_to_skips_post_and_uses_existing_actor(monkeypatch, tmp_path):
    """attach_to never POSTs a new run; reads actor from the existing record."""
    _baseline(monkeypatch, tmp_path)
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json",
               return_value=_existing_run("SUCCEEDED", 1.50)), \
         patch("apify_runner.runner._paginated_dataset_items",
               return_value=iter([{"a": 1}])), \
         patch("apify_runner.runner.time.sleep"):
        result = attach_to("run-existing", timeout_s=10, poll_interval_s=1)
    post.assert_not_called()
    assert result.run_id == "run-existing"
    assert result.actor == "apify/heavy"
    assert result.cost_usd == 1.50
    assert result.status == "SUCCEEDED"
    assert result.item_count == 1


def test_attach_to_jsonl_requires_output_path(monkeypatch, tmp_path):
    """attach_to honors the same fail-fast validation as run()."""
    _baseline(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        attach_to("run-x", dataset_mode="jsonl", output_path=None,
                  timeout_s=10, poll_interval_s=1)
