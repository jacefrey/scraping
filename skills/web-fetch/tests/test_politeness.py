"""Per-host politeness tests (spec §4.4)."""
import time
from unittest.mock import patch
from webfetch.politeness import HostPoliteness


def test_first_fetch_to_host_no_delay():
    p = HostPoliteness(min_delay_ms=500)
    with patch("webfetch.politeness.time.sleep") as sleep:
        p.wait_for("example.com")
    sleep.assert_not_called()


def test_second_fetch_within_window_sleeps():
    p = HostPoliteness(min_delay_ms=500)
    p._last_fetch["example.com"] = time.monotonic()
    with patch("webfetch.politeness.time.sleep") as sleep:
        p.wait_for("example.com")
    args, _ = sleep.call_args
    assert 0 <= args[0] <= 0.6


def test_different_hosts_independent_timers():
    p = HostPoliteness(min_delay_ms=500)
    p._last_fetch["a.com"] = time.monotonic()
    with patch("webfetch.politeness.time.sleep") as sleep:
        p.wait_for("b.com")
    sleep.assert_not_called()


def test_url_input_extracts_hostname():
    """wait_for accepts a full URL or a bare hostname."""
    p = HostPoliteness(min_delay_ms=500)
    p._last_fetch["example.com"] = time.monotonic()
    with patch("webfetch.politeness.time.sleep") as sleep:
        p.wait_for("https://example.com/some/path?query=1")
    sleep.assert_called_once()


def test_outside_window_no_sleep():
    """If the last fetch was >= min_delay_ms ago, no sleep."""
    p = HostPoliteness(min_delay_ms=500)
    p._last_fetch["example.com"] = time.monotonic() - 10.0  # 10 seconds ago
    with patch("webfetch.politeness.time.sleep") as sleep:
        p.wait_for("example.com")
    sleep.assert_not_called()
