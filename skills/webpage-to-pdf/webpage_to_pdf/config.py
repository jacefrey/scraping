"""Config loader (spec §6.7, §8.3, §8.10)."""
from __future__ import annotations
import hashlib
import json
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


_DEFAULTS: dict[str, Any] = {
    "render": {
        "page_format": "continuous",
        "render_mode": "live",
        "margin_in": 0.3,
        "flatten_sticky": "auto",
        "hide_fixed": False,
        "inject_page_break_avoid": "auto",
        "persist_rendered_html": True,
        "strip_selectors": [],
        "viewport": {
            "width_px": 1280,
            "height_px": 800,
        },
        "wait": {
            "strategy": "networkidle",
            "selector": "",
            "timeout_s": 10,
        },
        "lazy_load": {
            "scroll_pause_ms": 800,
            "max_scroll_steps": 50,
            "max_scroll_seconds": 30,
            "layout_settle_ms": 250,
        },
    }
}


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_toml(p: Path) -> dict[str, Any]:
    with p.open("rb") as f:
        return tomllib.load(f)


def load_config(toml_path: Path | None = None) -> dict[str, Any]:
    cfg = deepcopy(_DEFAULTS)
    candidates: list[Path] = []
    user_cfg = Path.home() / ".config" / "webpage-to-pdf.toml"
    if user_cfg.is_file():
        candidates.append(user_cfg)
    cwd_cfg = Path.cwd() / "webpage-to-pdf.toml"
    if cwd_cfg.is_file():
        candidates.append(cwd_cfg)
    if toml_path is not None:
        candidates.append(Path(toml_path))
    for p in candidates:
        cfg = _deep_merge(cfg, _load_toml(p))
    return cfg


def fingerprint(cfg: dict[str, Any]) -> str:
    payload = json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
