"""iter_items() — yields rows from an ApifyRunResult (spec §7.5).

Default: list mode reads result.items in-memory; jsonl mode streams the file.
refetch=True re-resolves auth and re-queries the dataset endpoint paginated.
"""
from __future__ import annotations
import json
from typing import Any, Iterator
from apify_runner import ENV_AUTODISCOVER
from apify_runner.client import _paginated_dataset_items
from apify_runner.env import resolve_apify_token
from apify_runner.result import ApifyRunResult


def iter_items(
    result: ApifyRunResult,
    *,
    refetch: bool = False,
    env_file: Any = ENV_AUTODISCOVER,
) -> Iterator[dict]:
    """Yield items from result.

    Default behavior:
        - jsonl mode (items_path is set) → stream the JSONL file line-by-line
        - list mode (items is populated) → yield from in-memory list

    refetch=True:
        Re-resolve auth via env_file (default ENV_AUTODISCOVER) and re-query
        the dataset endpoint with paginated reads. Useful only if the run is
        still appending rows after the original run() returned, which is rare.
        Returns empty iterator if result.dataset_id is None.
    """
    if refetch:
        if result.dataset_id is None:
            return
        token, _ = resolve_apify_token(env_file=env_file)
        yield from _paginated_dataset_items(
            result.api_base, dataset_id=result.dataset_id,
            token=token, limit=1000,
        )
        return

    if result.items_path is not None:
        with result.items_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        return

    yield from result.items
