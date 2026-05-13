"""Manifest JSONL writer (spec §8.10).

Single-process append, no file lock — concurrency is the caller's
responsibility per §11. Success and failure rows share the same shape;
failure rows have null source/derived/http_status/etc. fields.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from webpage_to_md import __version__ as WEBPAGE_TO_MD_VERSION

_MANIFEST_SCHEMA_VERSION = "1.0"
_ERROR_MESSAGE_CAP = 500


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _sanitize_error(message: str | None) -> str | None:
    if message is None:
        return None
    cleaned = " ".join(str(message).splitlines())
    return cleaned[:_ERROR_MESSAGE_CAP]


def append_manifest_row(
    manifest_path: Path,
    *,
    status: str,
    result: Any | None,
    source_artifact: str | None = None,
    derived_artifact: str | None = None,
    selector: str | None = None,
    extraction_strategy: str,
    config_sha256: str,
    duration_ms: float | int,
    error_category: str | None = None,
    error_message: str | None = None,
    # Used when result is None (failure rows):
    requested_url: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Append a JSON row to manifest.jsonl (spec §8.10)."""
    if result is not None:
        row = {
            "manifest_schema_version": _MANIFEST_SCHEMA_VERSION,
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "started_at": _iso(result.started_at),
            "completed_at": _iso(result.completed_at),
            "fetched_at": _iso(result.completed_at),
            "content_type": (result.content_type or "").split(";")[0].strip() or None,
            "content_type_source": result.content_type_source,
            "fetch_method": result.fetch_method,
            "http_status": result.http_status,
            "source_artifact": source_artifact,
            "source_sha256": result.content_hash_sha256,
            "derived_artifact": derived_artifact,
            "converter": "webpage-to-md",
            "converter_version": WEBPAGE_TO_MD_VERSION,
            "status": status,
            "error_category": error_category,
            "error_message": _sanitize_error(error_message),
            "duration_ms": int(duration_ms),
            "selector": selector,
            "extraction_strategy": extraction_strategy,
            "config_sha256": config_sha256,
        }
    else:
        row = {
            "manifest_schema_version": _MANIFEST_SCHEMA_VERSION,
            "requested_url": requested_url,
            "final_url": None,
            "started_at": _iso(started_at),
            "completed_at": _iso(completed_at),
            "fetched_at": None,
            "content_type": None,
            "content_type_source": None,
            "fetch_method": None,
            "http_status": None,
            "source_artifact": None,
            "source_sha256": None,
            "derived_artifact": None,
            "converter": "webpage-to-md",
            "converter_version": WEBPAGE_TO_MD_VERSION,
            "status": status,
            "error_category": error_category,
            "error_message": _sanitize_error(error_message),
            "duration_ms": int(duration_ms),
            "selector": selector,
            "extraction_strategy": extraction_strategy,
            "config_sha256": config_sha256,
        }
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
