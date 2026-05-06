"""Config loader for apify-runner (spec §7.6, §8.3)."""
from __future__ import annotations
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


_DEFAULTS: dict[str, Any] = {
    "apify": {
        "poll_interval_s": 5,
        "default_timeout_s": 600,
        "default_dataset_mode": "list",
        "max_dataset_items": 10000,
        "jsonl_max_dataset_items": 100000,
        "jsonl_max_dataset_bytes": 5_000_000_000,
        "abort_on_timeout": False,
        "strict_permissions": False,
        "api_base": "https://api.apify.com/v2",
        "cost_buffer_percent": 0,
        "dataset": {
            "on_partial": "rename",  # "rename" | "delete"
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
    """Resolve config. Precedence: explicit > CWD > ~/.config > defaults."""
    cfg = deepcopy(_DEFAULTS)
    candidates: list[Path] = []
    user_cfg = Path.home() / ".config" / "apify-runner.toml"
    if user_cfg.is_file():
        candidates.append(user_cfg)
    cwd_cfg = Path.cwd() / "apify-runner.toml"
    if cwd_cfg.is_file():
        candidates.append(cwd_cfg)
    if toml_path is not None:
        explicit = Path(toml_path)
        if not explicit.is_file():
            raise FileNotFoundError(
                f"apify-runner config not found at {explicit}. "
                f"Pass a valid path or omit toml_path to use defaults."
            )
        candidates.append(explicit)
    for p in candidates:
        cfg = _deep_merge(cfg, _load_toml(p))
    return cfg
