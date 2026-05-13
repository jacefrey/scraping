"""Sidecar JSON for local-re-render provenance (spec §5.3)."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat()


def write_meta_sidecar(path: Path, *, result: Any, web_fetch_version: str) -> None:
    payload = {
        "url": result.requested_url,
        "final_url": result.final_url,
        "fetched_at": _iso(result.completed_at),
        "fetch_method": result.fetch_method,
        "http_status": result.http_status,
        "content_type_source": result.content_type_source,
        "etag": getattr(result, "etag", None),
        "last_modified": getattr(result, "last_modified", None),
        "redirect_chain": list(getattr(result, "redirect_chain", []) or []),
        "source_sha256": result.content_hash_sha256,
        "web-fetch_version": web_fetch_version,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_meta_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
