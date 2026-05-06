"""run() happy-path test — mocked POST + polling + dataset retrieval."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from apify_runner.runner import run

FIXTURES = Path(__file__).parent / "fixtures"


def test_run_succeeds_returns_items(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok-test")

    run_started = json.loads((FIXTURES / "mock_run_response.json").read_text())
    run_succeeded = {**run_started}
    run_succeeded["data"] = {**run_started["data"]}
    run_succeeded["data"]["status"] = "SUCCEEDED"
    run_succeeded["data"]["finishedAt"] = "2026-05-04T10:00:05Z"
    run_succeeded["data"]["usage"] = {"totalUsd": 0.04}
    items = json.loads((FIXTURES / "mock_dataset_items.json").read_text())

    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items") as paginate, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = run_started
        get_json.return_value = run_succeeded
        paginate.return_value = iter(items)
        result = run(
            actor="apify/cheerio-scraper",
            input_data={"startUrls": [{"url": "https://example.com"}]},
            timeout_s=30, poll_interval_s=1,
        )

    assert result.run_id == "run-abc-123"
    assert result.actor == "apify/cheerio-scraper"
    assert result.dataset_id == "ds-xyz-789"
    assert result.status == "SUCCEEDED"
    assert result.item_count == 3
    assert result.cost_usd == 0.04
    assert result.items[0]["url"] == "https://example.com/a"
    assert result.items_path is None
