"""Config loader for web-fetch (spec §4.4, §8.3)."""
from __future__ import annotations
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


_DEFAULTS: dict[str, Any] = {
    "fetch": {
        "http_timeout_s": 10,
        "http_thin_threshold_bytes": 2048,
        "network_retries": 3,
        "http_timeout_retries": 2,
        "use_head": True,
        "head_timeout_s": 5,
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "max_redirects": 20,
        "return_blocked_content": False,
        "parse_safety": {
            "max_response_bytes": 50_000_000,
            "max_decoded_bytes": 200_000_000,
            "max_html_text_chars": 5_000_000,
        },
        "detection": {
            "challenge_markers": [],
        },
        "compression": {},
        "politeness": {
            "min_delay_ms_per_host": 500,
            "respect_retry_after": True,
            "max_retry_after_s": 120,
        },
        "playwright": {
            "timeout_s": 30,
            "playwright_timeout_retries": 1,
            "wait_for": "networkidle",
            "wait_for_selector": "",
            "extensions": [],
            "headless": True,
            "max_redirects": 20,
        },
        "conditional_get": {
            "enabled": False,
        },
        "domain_overrides": [],
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
    user_cfg = Path.home() / ".config" / "web-fetch.toml"
    if user_cfg.is_file():
        candidates.append(user_cfg)
    cwd_cfg = Path.cwd() / "web-fetch.toml"
    if cwd_cfg.is_file():
        candidates.append(cwd_cfg)
    if toml_path is not None:
        explicit = Path(toml_path)
        if not explicit.is_file():
            raise FileNotFoundError(
                f"web-fetch config not found at {explicit}. "
                f"Pass a valid path or omit toml_path to use defaults."
            )
        candidates.append(explicit)
    for p in candidates:
        cfg = _deep_merge(cfg, _load_toml(p))
    return cfg
