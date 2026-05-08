"""on_poll callback tests — fires once per poll, propagates exceptions."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from apify_runner.runner import run, attach_to

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok-test")


def _running_then_succeeded():
    """Two run records: one RUNNING (in-flight), then SUCCEEDED (terminal).
    The first poll returns RUNNING (callback fires); the second returns
    SUCCEEDED (callback fires again, then loop exits)."""
    base = json.loads((FIXTURES / "mock_run_response.json").read_text())
    running = {**base, "data": {**base["data"], "status": "RUNNING",
                                "usage": {"totalUsd": 0.01}}}
    succeeded = {**base, "data": {**base["data"], "status": "SUCCEEDED",
                                  "finishedAt": "2026-05-04T10:00:05Z",
                                  "usage": {"totalUsd": 0.04}}}
    return base, running, succeeded


def test_on_poll_fires_per_poll_with_status_and_record(monkeypatch, tmp_path):
    _seed_env(monkeypatch, tmp_path)
    base, running, succeeded = _running_then_succeeded()
    items = json.loads((FIXTURES / "mock_dataset_items.json").read_text())

    captured: list[tuple[str, dict]] = []
    def cb(status: str, record: dict) -> None:
        captured.append((status, record))

    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items") as paginate, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = base
        get_json.side_effect = [running, succeeded]
        paginate.return_value = iter(items)
        run(
            actor="apify/cheerio-scraper",
            input_data={"startUrls": [{"url": "https://example.com"}]},
            timeout_s=30, poll_interval_s=1,
            on_poll=cb,
        )

    # Two polls fire the callback: RUNNING (continues), SUCCEEDED (then loop exits).
    assert [s for s, _ in captured] == ["RUNNING", "SUCCEEDED"]
    assert captured[0][1]["id"] == "run-abc-123"
    assert captured[1][1]["status"] == "SUCCEEDED"
    assert captured[1][1]["usage"]["totalUsd"] == 0.04


def test_on_poll_default_none_no_invocation(monkeypatch, tmp_path):
    """on_poll omitted (default None) → no callback machinery, runs cleanly."""
    _seed_env(monkeypatch, tmp_path)
    base, _, succeeded = _running_then_succeeded()
    items = json.loads((FIXTURES / "mock_dataset_items.json").read_text())

    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items") as paginate, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = base
        get_json.return_value = succeeded
        paginate.return_value = iter(items)
        result = run(
            actor="apify/cheerio-scraper",
            input_data={},
            timeout_s=30, poll_interval_s=1,
        )
    assert result.status == "SUCCEEDED"


def test_on_poll_exception_propagates(monkeypatch, tmp_path):
    """Callback bugs surface — the runner does not swallow them."""
    _seed_env(monkeypatch, tmp_path)
    base, running, _ = _running_then_succeeded()

    def bad_cb(status: str, record: dict) -> None:
        raise RuntimeError("callback bug")

    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = base
        get_json.return_value = running
        with pytest.raises(RuntimeError, match="callback bug"):
            run(
                actor="apify/cheerio-scraper", input_data={},
                timeout_s=30, poll_interval_s=1,
                on_poll=bad_cb,
            )


def test_on_poll_threaded_through_attach_to(monkeypatch, tmp_path):
    """attach_to() also accepts on_poll and threads it through."""
    _seed_env(monkeypatch, tmp_path)
    base, running, succeeded = _running_then_succeeded()
    items = json.loads((FIXTURES / "mock_dataset_items.json").read_text())

    captured: list[str] = []
    def cb(status: str, record: dict) -> None:
        captured.append(status)

    with patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items") as paginate, \
         patch("apify_runner.runner.time.sleep"):
        # attach_to does an initial GET to read the run record (returns the
        # in-flight one), then polls until terminal.
        get_json.side_effect = [base, running, succeeded]
        paginate.return_value = iter(items)
        attach_to("run-abc-123", timeout_s=30, poll_interval_s=1, on_poll=cb)

    assert captured == ["RUNNING", "SUCCEEDED"]
