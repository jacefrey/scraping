"""iter_items tests (spec §7.5)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import pytest
from apify_runner import ENV_AUTODISCOVER
from apify_runner.iter_items import iter_items
from apify_runner.result import ApifyRunResult


def _make_result(items=None, items_path=None):
    return ApifyRunResult(
        run_id="r1", actor="apify/x", dataset_id="ds-1",
        api_base="https://api.apify.com/v2",
        status="SUCCEEDED", items=items or [], items_path=items_path,
        item_count=len(items or []) if items_path is None else 0,
        cost_usd=0.0, duration_s=1.0,
        started_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )


def test_iter_items_list_mode_reads_in_memory():
    r = _make_result(items=[{"a": 1}, {"a": 2}])
    out = list(iter_items(r))
    assert out == [{"a": 1}, {"a": 2}]


def test_iter_items_jsonl_mode_reads_file(tmp_path):
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join([json.dumps({"x": i}) for i in range(3)]) + "\n")
    r = _make_result(items_path=p)
    out = list(iter_items(r))
    assert out == [{"x": 0}, {"x": 1}, {"x": 2}]


def test_iter_items_refetch_re_resolves_auth_and_paginates(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("APIFY_API_TOKEN", "tok-fresh")
    r = _make_result(items=[])  # original was list mode — empty
    fresh = [{"new": i} for i in range(2)]
    with patch("apify_runner.iter_items._paginated_dataset_items",
               return_value=iter(fresh)):
        out = list(iter_items(r, refetch=True))
    assert out == fresh


def test_iter_items_refetch_no_dataset_id_returns_empty():
    """When dataset_id is None, refetch yields nothing (graceful degrade)."""
    r = _make_result(items=[])
    r.dataset_id = None
    out = list(iter_items(r, refetch=True))
    assert out == []


def test_iter_items_jsonl_skips_blank_lines(tmp_path):
    """Blank lines in JSONL file are silently skipped."""
    p = tmp_path / "items.jsonl"
    p.write_text(
        '{"a": 1}\n'
        '\n'
        '{"a": 2}\n'
        '   \n'
        '{"a": 3}\n'
    )
    r = _make_result(items_path=p)
    out = list(iter_items(r))
    assert out == [{"a": 1}, {"a": 2}, {"a": 3}]
