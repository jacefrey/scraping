"""Apify run orchestration — POST, poll, retrieve dataset (spec §7.1, §7.2)."""
from __future__ import annotations
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from apify_runner import ENV_AUTODISCOVER
from apify_runner._clock import _clock
from apify_runner.client import (
    _post_json, _get_json, _abort_run, _paginated_dataset_items, ApifyHttpError,
)
from apify_runner.config import load_config
from apify_runner.env import resolve_apify_token
from apify_runner.errors import (
    ApifyActorNotFoundError, ApifyAuthError,
    ApifyRunFailedError, ApifyTimeoutError,
)
from apify_runner.result import ApifyRunResult

_TERMINAL_STATUSES = {"SUCCEEDED", "FINISHED", "FAILED", "TIMED-OUT", "ABORTED"}
_NONTERMINAL_STATUSES = {"READY", "RUNNING", "PENDING"}


def _parse_apify_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def run(
    actor: str,
    input_data: dict | None,
    *,
    timeout_s: int = 600,
    poll_interval_s: int = 5,
    abort_on_timeout: bool = False,
    max_cost_usd: float | None = None,
    cost_buffer_percent: float = 0,
    dataset_mode: str = "list",
    output_path: Path | None = None,
    env_file: Any = ENV_AUTODISCOVER,
    cfg: dict | None = None,
) -> ApifyRunResult:
    """Execute an Apify actor and return ApifyRunResult (spec §7.1)."""
    if cfg is None:
        cfg = load_config()
    apify = cfg["apify"]
    token, _ = resolve_apify_token(
        env_file=env_file,
        strict_permissions=apify.get("strict_permissions", False),
    )
    api_base = apify["api_base"]

    # POST /v2/acts/{actor}/runs
    try:
        post_url = f"{api_base.rstrip('/')}/acts/{actor}/runs"
        run_payload = _post_json(post_url, token=token, body=input_data or {})
    except ApifyHttpError as e:
        if e.status == 401:
            raise ApifyAuthError("apify rejected token (401)") from e
        if e.status == 404:
            raise ApifyActorNotFoundError(
                f"actor {actor} not found", actor=actor
            ) from e
        raise

    rdata = run_payload["data"]
    run_id = rdata["id"]
    dataset_id = rdata.get("defaultDatasetId")
    started_at = _parse_apify_dt(rdata.get("startedAt")) or _clock()

    # Poll until terminal or timeout
    poll_start = time.monotonic()
    last_status = rdata.get("status", "READY")
    last_cost = float(rdata.get("usage", {}).get("totalUsd", 0.0))
    finished_at: datetime | None = None
    while True:
        if last_status in _TERMINAL_STATUSES:
            break
        elapsed = time.monotonic() - poll_start
        if elapsed > timeout_s:
            aborted = False
            if abort_on_timeout:
                try:
                    _abort_run(api_base, run_id=run_id, token=token)
                    aborted = True
                except ApifyHttpError:
                    aborted = False
            raise ApifyTimeoutError(
                f"run {run_id} timed out at status={last_status}, "
                f"cost ${last_cost:.4f}",
                run_id=run_id, actor=actor, status_at_timeout=last_status,
                cost_usd_at_timeout=last_cost, dataset_id=dataset_id,
                aborted=aborted,
            )
        time.sleep(poll_interval_s)
        get_url = f"{api_base.rstrip('/')}/actor-runs/{run_id}"
        try:
            poll = _get_json(get_url, token=token)
        except ApifyHttpError:
            # Transient; let the timeout loop catch it.
            continue
        pdata = poll["data"]
        last_status = pdata.get("status", last_status)
        last_cost = float(pdata.get("usage", {}).get("totalUsd", last_cost))
        if pdata.get("finishedAt"):
            finished_at = _parse_apify_dt(pdata["finishedAt"])

    if last_status in {"FAILED", "ABORTED"}:
        raise ApifyRunFailedError(
            f"run {run_id} ended {last_status}",
            run_id=run_id, actor=actor, status=last_status,
            cost_usd_at_failure=last_cost, dataset_id=dataset_id,
        )

    # Retrieve dataset (list mode only at this task; jsonl in A.2.8)
    items: list[dict] = []
    if dataset_id is not None:
        max_items = apify["max_dataset_items"]
        for item in _paginated_dataset_items(
            api_base, dataset_id=dataset_id, token=token, limit=1000,
        ):
            items.append(item)
            if len(items) >= max_items:
                break

    finished_at = finished_at or _clock()
    duration = (finished_at - started_at).total_seconds() if started_at else 0.0

    return ApifyRunResult(
        run_id=run_id,
        actor=actor,
        dataset_id=dataset_id,
        api_base=api_base,
        status=last_status,
        items=items,
        items_path=None,
        item_count=len(items),
        cost_usd=last_cost,
        duration_s=duration,
        started_at=started_at,
        finished_at=finished_at,
    )
