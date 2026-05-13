"""Config loader for webpage-to-md (spec §5.10, §8.3) + fingerprint() (spec §5.4)."""
from __future__ import annotations
import hashlib
import json
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


_DEFAULTS: dict[str, Any] = {
    "convert": {
        "emit_frontmatter": True,
        "default_selector": "",
        "extraction": {
            "strategy": "selector_then_body",
        },
        "html_to_md": {
            "strip_classes": ["ad", "newsletter-signup", "social-share"],
            "strip_selectors": [],
            "preserve_classes": [],
            "heading_style": "ATX",
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
    """Resolve config. Precedence: explicit > CWD > ~/.config > defaults (spec §8.3)."""
    cfg = deepcopy(_DEFAULTS)
    candidates: list[Path] = []
    user_cfg = Path.home() / ".config" / "webpage-to-md.toml"
    if user_cfg.is_file():
        candidates.append(user_cfg)
    cwd_cfg = Path.cwd() / "webpage-to-md.toml"
    if cwd_cfg.is_file():
        candidates.append(cwd_cfg)
    if toml_path is not None:
        candidates.append(Path(toml_path))
    for p in candidates:
        cfg = _deep_merge(cfg, _load_toml(p))
    return cfg


def fingerprint(cfg: dict[str, Any]) -> str:
    """SHA-256 hex digest of the resolved config (spec §5.4, §8.10).

    Recorded in frontmatter and manifest rows as `config_sha256` so two runs
    with different effective configs can be distinguished.
    """
    payload = json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
