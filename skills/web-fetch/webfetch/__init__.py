"""web-fetch — URL to bytes with HTTP→Playwright auto-fallback. See SKILL.md."""
from __future__ import annotations
from typing import Any
from urllib.parse import urlparse

from webfetch.config import load_config
from webfetch.detect import is_thin_shell
from webfetch.http import http_fetch
from webfetch.playwright_fetch import playwright_fetch
from webfetch.politeness import HostPoliteness
from webfetch.result import (
    FetchResult,
    FetchError,
    ContentTypeSource,
    FetchMethod,
)

__version__ = "0.1.0"
__all__ = [
    "fetch",
    "FetchResult",
    "FetchError",
    "ContentTypeSource",
    "FetchMethod",
    "__version__",
]

# Module-level singleton — shared across fetch() calls within one process.
#
# IMPORTANT: _GLOBAL_POLITENESS is initialized from the FIRST cfg passed to
# fetch(). Subsequent calls with different `min_delay_ms_per_host` values
# are silently ignored — the process-wide delay cannot be changed after
# first initialization. This is intentional (process-singleton design) but
# callers using divergent cfgs in one process should be aware.
#
# See HostPoliteness docstring for thread-safety + memory caveats.
# A future reset_politeness() API may be added if long-running consumers
# need to evict stale per-host timestamps or rotate delays.
_GLOBAL_POLITENESS: HostPoliteness | None = None


def _get_politeness(cfg: dict[str, Any]) -> HostPoliteness:
    """Lazily construct the per-process HostPoliteness instance."""
    global _GLOBAL_POLITENESS
    if _GLOBAL_POLITENESS is None:
        _GLOBAL_POLITENESS = HostPoliteness(
            min_delay_ms=cfg["fetch"]["politeness"]["min_delay_ms_per_host"]
        )
    return _GLOBAL_POLITENESS


def _resolve_method(url: str, fetch_method: str, cfg: dict[str, Any]) -> str:
    """Spec §4.1 precedence: explicit fetch_method > domain override > auto.

    Domain overrides with fetch_method="auto" are silently skipped — they're
    a no-op and likely a config error. The function falls through to the
    standard auto path.
    """
    if fetch_method != "auto":
        return fetch_method
    host = urlparse(url).hostname or ""
    for override in cfg["fetch"].get("domain_overrides", []):
        if override.get("host") == host:
            override_method = override.get("fetch_method", "auto")
            if override_method != "auto":
                return override_method
    return "auto"


def fetch(
    url: str,
    *,
    fetch_method: str = "auto",
    return_blocked_content: bool = False,
    if_none_match: str | None = None,
    if_modified_since: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> FetchResult:
    """Fetch URL. See spec §4.1 / §4.2.

    Args:
        url: requested URL.
        fetch_method: "auto" (default; uses §4.2 ladder) | "http" | "playwright".
        return_blocked_content: when True, surface bot_challenge / auth_required
            as a partial FetchResult (with error_category set) instead of raising.
        if_none_match: ETag — accepted-but-ignored in MVP; reserved for v0.2.
        if_modified_since: HTTP-date — accepted-but-ignored in MVP; reserved for v0.2.
        cfg: optional config dict from load_config(); loaded fresh if None.

    Returns:
        FetchResult on success or surfaced partial.

    Raises:
        ValueError if fetch_method is not one of "auto" / "http" / "playwright".
        FetchError on terminal failure. See result.FetchError.error_category.
    """
    # Argument validation first — fail fast before any cfg load, politeness
    # sleep, or network side effect. Mirrors apify-runner's run() pattern.
    if fetch_method not in ("auto", "http", "playwright"):
        raise ValueError(
            f'fetch_method must be "auto", "http", or "playwright"; '
            f"got {fetch_method!r}"
        )
    if cfg is None:
        cfg = load_config()
    if return_blocked_content:
        # Don't mutate the caller's cfg — they may reuse it across calls.
        # Shallow copy is sufficient here since the override is a scalar
        # at a single nested key.
        cfg = {**cfg, "fetch": {**cfg["fetch"], "return_blocked_content": True}}

    # Per-host politeness wait BEFORE dispatch (so the fetch path doesn't
    # need to know about it).
    politeness = _get_politeness(cfg)
    politeness.wait_for(url)

    method = _resolve_method(url, fetch_method, cfg)
    if method == "playwright":
        return playwright_fetch(url, cfg=cfg)
    if method == "http":
        return http_fetch(url, cfg=cfg)

    # Auto: HTTP first; thin-shell triggers Playwright fallback (spec §4.2 step 6).
    result = http_fetch(url, cfg=cfg)
    if (
        result.error_category is None
        and (result.content_type or "").lower().startswith("text/html")
        and is_thin_shell(
            result.content,
            http_thin_threshold_bytes=cfg["fetch"]["http_thin_threshold_bytes"],
            max_html_text_chars=cfg["fetch"]["parse_safety"]["max_html_text_chars"],
        )
    ):
        return playwright_fetch(url, cfg=cfg)
    return result
