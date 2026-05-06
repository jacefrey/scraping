"""ApifyRunResult — public type returned by run() / attach_to() (spec §7.1)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ApifyRunResult:
    run_id: str
    actor: str
    dataset_id: str | None
    api_base: str
    status: str  # "SUCCEEDED" | "FAILED" | "TIMED-OUT" | "ABORTED"
    items: list[dict]
    items_path: Path | None
    item_count: int
    cost_usd: float
    duration_s: float
    started_at: datetime
    finished_at: datetime
