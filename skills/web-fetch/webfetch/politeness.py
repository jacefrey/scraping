"""Per-host politeness — keeps a last-fetch timestamp per host (spec §4.4).

Per-process scope. Multi-process bulk callers must coordinate cross-process
rate limits externally (out of scope per spec §1.5).
"""
from __future__ import annotations
import time
from urllib.parse import urlparse


class HostPoliteness:
    """Tracks last-fetch time per host and sleeps to enforce a minimum delay.

    Usage:
        p = HostPoliteness(min_delay_ms=500)
        p.wait_for("https://example.com/article")  # may sleep
        # ... fetch happens here ...
        p.wait_for("https://example.com/other")    # may sleep again

    The wait_for() method records the timestamp AFTER any sleep, so the
    delay window starts when the call returns (right before the actual
    fetch begins). This intentionally over-counts slightly — the recorded
    "last_fetch" includes the wait itself — which biases toward more
    politeness, never less.

    Thread safety: _last_fetch is not protected by a lock. Safe for
    single-threaded callers (the expected usage via fetch() in A.1.13).
    If the orchestrator ever uses threads, add a threading.Lock around
    the read/write pair in wait_for().

    Memory: _last_fetch grows unbounded. For long-lived processes hitting
    thousands of distinct hosts, add an LRU eviction cap (TODO).
    """

    def __init__(self, min_delay_ms: int) -> None:
        self.min_delay_s = min_delay_ms / 1000.0
        self._last_fetch: dict[str, float] = {}

    def wait_for(self, host_or_url: str) -> None:
        """Block as needed before a fetch to the given host/URL.

        Accepts either a bare hostname ("example.com") or a full URL
        ("https://example.com/path"). The hostname is extracted via urlparse.
        Per-host timer; different hosts have independent windows.

        urlparse returns hostname=None for bare hostnames (e.g. "example.com"
        is parsed as a path, not a netloc); the `or host_or_url` fallback
        uses the raw string as the key, which is correct for that input.
        """
        host = urlparse(host_or_url).hostname or host_or_url
        now = time.monotonic()
        last = self._last_fetch.get(host)
        if last is not None:
            elapsed = now - last
            if elapsed < self.min_delay_s:
                time.sleep(self.min_delay_s - elapsed)
        self._last_fetch[host] = time.monotonic()
