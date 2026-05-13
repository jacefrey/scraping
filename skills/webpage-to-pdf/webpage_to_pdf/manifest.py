"""JSONL manifest writer for webpage-to-pdf (spec §8.10)."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from webpage_to_pdf import __version__ as WEBPAGE_TO_PDF_VERSION

_MANIFEST_SCHEMA_VERSION = "1.0"
_ERROR_CAP = 500


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat()


def _sanitize(msg: str | None) -> str | None:
    if msg is None:
        return None
    return " ".join(str(msg).splitlines())[:_ERROR_CAP]


def append_manifest_row(
    manifest_path: Path,
    *,
    status: str,
    result: Any | None,
    source_artifact: str | None = None,
    derived_artifact: str | None = None,
    selector: str | None = None,
    config_sha256: str,
    duration_ms: float | int,
    error_category: str | None = None,
    error_message: str | None = None,
    # webpage-to-pdf extras (§8.10)
    render_mode: str | None = None,
    page_format: Any = None,
    flatten_sticky: bool | None = None,
    hide_fixed: bool | None = None,
    live_double_fetch: bool | None = None,
    render_html_sha256: str | None = None,
    rendered_html_artifact: str | None = None,
    passthrough: bool = False,
    # Used when result is None (failure rows)
    requested_url: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    common = {
        "manifest_schema_version": _MANIFEST_SCHEMA_VERSION,
        "converter": "webpage-to-pdf",
        "converter_version": WEBPAGE_TO_PDF_VERSION,
        "status": status,
        "error_category": error_category,
        "error_message": _sanitize(error_message),
        "duration_ms": int(duration_ms),
        "selector": selector,
        "config_sha256": config_sha256,
        "render_mode": render_mode,
        "page_format": page_format,
        "flatten_sticky": flatten_sticky,
        "hide_fixed": hide_fixed,
        "live_double_fetch": live_double_fetch,
        "render_html_sha256": render_html_sha256,
        "rendered_html_artifact": rendered_html_artifact,
        "passthrough": passthrough,
    }
    if result is not None:
        row = {
            **common,
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
        }
    else:
        row = {
            **common,
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
        }
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
