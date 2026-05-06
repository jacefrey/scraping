"""Apify run orchestration — POST, poll, retrieve dataset (spec §7.1, §7.2)."""
from __future__ import annotations
import json
import os
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
    ApifyActorNotFoundError, ApifyAuthError, ApifyBudgetExceededError,
    ApifyDatasetError, ApifyRunFailedError, ApifyTimeoutError,
)
from apify_runner.result import ApifyRunResult

_TERMINAL_STATUSES = {"SUCCEEDED", "FINISHED", "FAILED", "TIMED-OUT", "ABORTED"}
_NONTERMINAL_STATUSES = {"READY", "RUNNING", "PENDING"}


def _parse_apify_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _poll_and_collect(
    *,
    run_id: str,
    actor: str,
    dataset_id: str | None,
    token: str,
    api_base: str,
    apify_cfg: dict[str, Any],
    timeout_s: int,
    poll_interval_s: int,
    abort_on_timeout: bool,
    max_cost_usd: float | None,
    cost_buffer_percent: float,
    dataset_mode: str,
    output_path: Path | None,
    initial_status: str,
    initial_cost: float,
    started_at: datetime,
) -> ApifyRunResult:
    """Shared polling loop + dataset retrieval used by run() and attach_to().

    Both entry points reach this function with the run_id, actor, and
    dataset_id already known. Polls until the run reaches a terminal status
    (or the local timeout), then retrieves the dataset in list or jsonl mode.
    """
    poll_start = time.monotonic()
    last_status = initial_status
    last_cost = initial_cost
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

        # Spec §7.7: budget gate (best-effort; reported usage lags actual cost).
        if max_cost_usd is not None:
            effective_cap = max_cost_usd * (1 - cost_buffer_percent / 100.0)
            if last_cost > effective_cap:
                try:
                    _abort_run(api_base, run_id=run_id, token=token)
                except ApifyHttpError:
                    pass  # best-effort
                raise ApifyBudgetExceededError(
                    f"run {run_id} exceeded budget ${last_cost:.2f} > "
                    f"${effective_cap:.2f} (cap ${max_cost_usd:.2f}, "
                    f"buffer {cost_buffer_percent}%)",
                    run_id=run_id, actor=actor, cost_usd=last_cost,
                    max_cost_usd=max_cost_usd, dataset_id=dataset_id,
                )

    if last_status in {"FAILED", "ABORTED"}:
        raise ApifyRunFailedError(
            f"run {run_id} ended {last_status}",
            run_id=run_id, actor=actor, status=last_status,
            cost_usd_at_failure=last_cost, dataset_id=dataset_id,
        )

    # Retrieve dataset — list mode (in-memory) or jsonl (atomic streaming write).
    items: list[dict] = []
    items_path: Path | None = None
    item_count = 0

    if dataset_mode == "jsonl":
        if output_path is None:
            raise ValueError("dataset_mode='jsonl' requires output_path")
        output_path = Path(output_path)
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        cap_items = apify_cfg["jsonl_max_dataset_items"]
        cap_bytes = apify_cfg["jsonl_max_dataset_bytes"]
        on_partial = apify_cfg["dataset"].get("on_partial", "rename")
        written = 0
        written_bytes = 0
        cap_exceeded = False
        if dataset_id is not None:
            with tmp_path.open("w", encoding="utf-8") as f:
                for item in _paginated_dataset_items(
                    api_base, dataset_id=dataset_id, token=token, limit=1000,
                ):
                    line = json.dumps(item, ensure_ascii=False) + "\n"
                    line_bytes = line.encode("utf-8")
                    if written >= cap_items or (written_bytes + len(line_bytes)) > cap_bytes:
                        cap_exceeded = True
                        break
                    f.write(line)
                    written += 1
                    written_bytes += len(line_bytes)
        if cap_exceeded:
            # Run already terminated successfully — stop retrieval, no abort call.
            if on_partial == "delete":
                tmp_path.unlink(missing_ok=True)
            else:
                partial = output_path.with_suffix(output_path.suffix + ".partial.jsonl")
                tmp_path.replace(partial)
            raise ApifyDatasetError(
                f"dataset cap exceeded after {written} items",
                run_id=run_id, actor=actor, dataset_id=dataset_id,
                items_retrieved=written, cause="cap_exceeded",
            )
        # Atomic rename on success.
        os.replace(tmp_path, output_path)
        items_path = output_path
        item_count = written
    else:
        # list mode: in-memory items list, capped at max_dataset_items.
        if dataset_id is not None:
            max_items = apify_cfg["max_dataset_items"]
            for item in _paginated_dataset_items(
                api_base, dataset_id=dataset_id, token=token, limit=1000,
            ):
                items.append(item)
                if len(items) >= max_items:
                    break
        item_count = len(items)

    finished_at = finished_at or _clock()
    duration = (finished_at - started_at).total_seconds() if started_at else 0.0

    return ApifyRunResult(
        run_id=run_id,
        actor=actor,
        dataset_id=dataset_id,
        api_base=api_base,
        status=last_status,
        items=items,
        items_path=items_path,
        item_count=item_count,
        cost_usd=last_cost,
        duration_s=duration,
        started_at=started_at,
        finished_at=finished_at,
    )


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
    # Argument validation first — fail fast before any auth or network side effects.
    if dataset_mode == "jsonl" and output_path is None:
        raise ValueError("dataset_mode='jsonl' requires output_path")

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
    initial_status = rdata.get("status", "READY")
    initial_cost = float(rdata.get("usage", {}).get("totalUsd", 0.0))

    return _poll_and_collect(
        run_id=run_id, actor=actor, dataset_id=dataset_id,
        token=token, api_base=api_base, apify_cfg=apify,
        timeout_s=timeout_s, poll_interval_s=poll_interval_s,
        abort_on_timeout=abort_on_timeout,
        max_cost_usd=max_cost_usd, cost_buffer_percent=cost_buffer_percent,
        dataset_mode=dataset_mode, output_path=output_path,
        initial_status=initial_status, initial_cost=initial_cost,
        started_at=started_at,
    )


def attach_to(
    run_id: str,
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
    """Attach to an existing Apify run (spec §7.1).

    Reads actor + dataset_id from the existing run record. No POST is issued
    — the caller has already paid for the existing run, this just resumes
    polling against it. Useful when the original run() timed out locally
    but the run is still going on Apify's infrastructure.
    """
    if dataset_mode == "jsonl" and output_path is None:
        raise ValueError("dataset_mode='jsonl' requires output_path")

    if cfg is None:
        cfg = load_config()
    apify = cfg["apify"]
    token, _ = resolve_apify_token(
        env_file=env_file,
        strict_permissions=apify.get("strict_permissions", False),
    )
    api_base = apify["api_base"]

    # Read the existing run record. No POST.
    run_url = f"{api_base.rstrip('/')}/actor-runs/{run_id}"
    record = _get_json(run_url, token=token)
    rdata = record["data"]
    actor = rdata.get("actId", "<unknown>")
    dataset_id = rdata.get("defaultDatasetId")
    initial_status = rdata.get("status", "READY")
    initial_cost = float(rdata.get("usage", {}).get("totalUsd", 0.0))
    started_at = _parse_apify_dt(rdata.get("startedAt")) or _clock()

    return _poll_and_collect(
        run_id=run_id, actor=actor, dataset_id=dataset_id,
        token=token, api_base=api_base, apify_cfg=apify,
        timeout_s=timeout_s, poll_interval_s=poll_interval_s,
        abort_on_timeout=abort_on_timeout,
        max_cost_usd=max_cost_usd, cost_buffer_percent=cost_buffer_percent,
        dataset_mode=dataset_mode, output_path=output_path,
        initial_status=initial_status, initial_cost=initial_cost,
        started_at=started_at,
    )
