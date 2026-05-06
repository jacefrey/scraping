"""JSONL atomic-write tests (spec §7.5)."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from apify_runner.runner import run
from apify_runner.errors import ApifyDatasetError


def _baseline(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")


def _started():
    return {"data": {"id": "run-1", "actId": "apify/x",
                     "defaultDatasetId": "ds-1", "status": "READY",
                     "startedAt": "2026-05-04T10:00:00Z",
                     "finishedAt": None, "usage": {"totalUsd": 0.0}}}


def _ok():
    return {"data": {"id": "run-1", "actId": "apify/x",
                     "defaultDatasetId": "ds-1", "status": "SUCCEEDED",
                     "startedAt": "2026-05-04T10:00:00Z",
                     "finishedAt": "2026-05-04T10:00:05Z",
                     "usage": {"totalUsd": 0.05}}}


def test_jsonl_atomic_write_renames_on_success(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    out = tmp_path / "items.jsonl"
    items = [{"x": i} for i in range(3)]
    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items") as paginate, \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started()
        get_json.return_value = _ok()
        paginate.return_value = iter(items)
        result = run(
            actor="apify/x", input_data={}, dataset_mode="jsonl",
            output_path=out, timeout_s=10, poll_interval_s=1,
        )
    assert result.items == []          # list-mode-style items list is empty in jsonl mode
    assert result.items_path == out
    assert result.item_count == 3
    assert out.exists()
    assert not (tmp_path / "items.jsonl.tmp").exists()
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0]) == {"x": 0}


def test_jsonl_cap_exceeded_terminal_run_stops_retrieval(monkeypatch, tmp_path):
    """Spec §7.5: if cap exceeded AFTER run terminated SUCCESSFUL, stop
    retrieval and raise — do not call abort against an already-terminal run."""
    _baseline(monkeypatch, tmp_path)
    out = tmp_path / "items.jsonl"
    big = [{"x": i} for i in range(10)]

    def _generator():
        for item in big:
            yield item

    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._abort_run") as abort, \
         patch("apify_runner.runner._paginated_dataset_items",
               return_value=_generator()), \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started()
        get_json.return_value = _ok()
        from apify_runner.config import load_config
        cfg = load_config()
        cfg["apify"]["jsonl_max_dataset_items"] = 3  # tighten cap for test
        with pytest.raises(ApifyDatasetError) as exc:
            run(actor="apify/x", input_data={}, dataset_mode="jsonl",
                output_path=out, timeout_s=10, poll_interval_s=1, cfg=cfg)
    abort.assert_not_called()  # run already terminal — never call abort
    assert exc.value.cause == "cap_exceeded"
    assert exc.value.items_retrieved == 3
    # Partial file lives at .partial.jsonl (default on_partial = "rename")
    assert (tmp_path / "items.jsonl.partial.jsonl").exists()
    assert not out.exists()


def test_jsonl_cap_exceeded_delete_mode(monkeypatch, tmp_path):
    """on_partial = 'delete' should remove the .tmp file on cap-exceeded."""
    _baseline(monkeypatch, tmp_path)
    out = tmp_path / "items.jsonl"
    big = [{"x": i} for i in range(10)]

    with patch("apify_runner.runner._post_json") as post, \
         patch("apify_runner.runner._get_json") as get_json, \
         patch("apify_runner.runner._paginated_dataset_items",
               return_value=iter(big)), \
         patch("apify_runner.runner.time.sleep"):
        post.return_value = _started()
        get_json.return_value = _ok()
        from apify_runner.config import load_config
        cfg = load_config()
        cfg["apify"]["jsonl_max_dataset_items"] = 3
        cfg["apify"]["dataset"]["on_partial"] = "delete"
        with pytest.raises(ApifyDatasetError):
            run(actor="apify/x", input_data={}, dataset_mode="jsonl",
                output_path=out, timeout_s=10, poll_interval_s=1, cfg=cfg)
    assert not (tmp_path / "items.jsonl.tmp").exists()
    assert not (tmp_path / "items.jsonl.partial.jsonl").exists()
    assert not out.exists()


def test_jsonl_requires_output_path(monkeypatch, tmp_path):
    _baseline(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        run(actor="apify/x", input_data={}, dataset_mode="jsonl",
            output_path=None, timeout_s=10, poll_interval_s=1)
