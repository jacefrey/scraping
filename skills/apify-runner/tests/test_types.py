"""Tests for ApifyRunResult + error hierarchy (spec §7.1, §7.4)."""
from datetime import datetime, timezone
import pytest
from apify_runner.result import ApifyRunResult
from apify_runner.errors import (
    ApifyError, ApifyAuthError, ApifyActorNotFoundError,
    ApifyRunFailedError, ApifyTimeoutError, ApifyBudgetExceededError,
    ApifyDatasetError,
)


def test_run_result_required_fields():
    started = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 5, 4, 10, 0, 5, tzinfo=timezone.utc)
    r = ApifyRunResult(
        run_id="abc123", actor="apify/cheerio-scraper",
        dataset_id="ds1", api_base="https://api.apify.com/v2",
        status="SUCCEEDED", items=[{"x": 1}], items_path=None,
        item_count=1, cost_usd=0.05, duration_s=5.0,
        started_at=started, finished_at=finished,
    )
    assert r.run_id == "abc123"
    assert r.item_count == 1
    assert r.status == "SUCCEEDED"


def test_error_hierarchy_inheritance():
    for cls in [ApifyAuthError, ApifyActorNotFoundError,
                ApifyRunFailedError, ApifyTimeoutError,
                ApifyBudgetExceededError, ApifyDatasetError]:
        assert issubclass(cls, ApifyError)


def test_timeout_error_carries_run_id():
    err = ApifyTimeoutError(
        message="timed out at READY",
        run_id="abc123", actor="apify/heavy",
        status_at_timeout="READY", cost_usd_at_timeout=0.42,
        dataset_id="ds1", aborted=False,
    )
    assert err.run_id == "abc123"
    assert err.cost_usd_at_timeout == 0.42
    assert err.aborted is False


def test_budget_error_carries_cap_and_cost():
    err = ApifyBudgetExceededError(
        message="exceeded budget",
        run_id="x", actor="a", cost_usd=2.10,
        max_cost_usd=2.00, dataset_id=None,
    )
    assert err.cost_usd == 2.10
    assert err.max_cost_usd == 2.00
