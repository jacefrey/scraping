"""Playwright render tests — all Playwright calls mocked (spec §6.3, §6.5, §6.6)."""
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from webpage_to_pdf.pdf_render import (
    run_lazy_load_loop,
    flatten_sticky_elements,
    hide_fixed_elements,
    render_pdf,
)


def _mock_page(scroll_heights=None):
    """Build a fake Playwright Page object whose evaluate() returns scripted values."""
    page = MagicMock()
    heights = list(scroll_heights or [3000, 3000])  # stable immediately
    page.evaluate = MagicMock()

    def evaluate(script, *args, **kwargs):
        if "scrollHeight" in script:
            return heights.pop(0) if heights else 3000
        return None

    page.evaluate.side_effect = evaluate
    return page


def test_lazy_load_loop_stops_when_height_stable():
    """Spec §6.5: stableCount >= 2 exits the loop early."""
    # Heights: 1000, 2000, 2000, 2000 (two stables → exit)
    page = _mock_page(scroll_heights=[1000, 2000, 2000, 2000])
    steps = run_lazy_load_loop(
        page,
        cfg={"render": {"lazy_load": {
            "scroll_pause_ms": 1,
            "max_scroll_steps": 50,
            "max_scroll_seconds": 30,
            "layout_settle_ms": 1,
        }}},
    )
    assert steps < 50


def test_lazy_load_loop_respects_max_steps():
    """Loop caps at max_scroll_steps when scrollHeight keeps growing."""
    growing = [i * 100 for i in range(100)]
    page = _mock_page(scroll_heights=growing)
    steps = run_lazy_load_loop(
        page,
        cfg={"render": {"lazy_load": {
            "scroll_pause_ms": 1,
            "max_scroll_steps": 5,
            "max_scroll_seconds": 30,
            "layout_settle_ms": 1,
        }}},
    )
    assert steps == 5


def test_flatten_sticky_runs_compute_style_walk():
    """Spec §6.6: implementation uses getComputedStyle walk, not [style*='...']."""
    page = MagicMock()
    flatten_sticky_elements(page)
    page.evaluate.assert_called_once()
    script = page.evaluate.call_args[0][0]
    assert "getComputedStyle" in script
    assert "position" in script
    assert "static" in script
    assert "originalPosition" in script


def test_hide_fixed_sets_display_none():
    page = MagicMock()
    hide_fixed_elements(page)
    page.evaluate.assert_called_once()
    script = page.evaluate.call_args[0][0]
    assert "display" in script
    assert "none" in script


def test_render_pdf_calls_playwright_pdf_with_print_opts(tmp_path):
    """render_pdf calls page.pdf(...) with width/height/print_background/margin."""
    page = MagicMock()
    out_pdf = tmp_path / "x.pdf"
    render_pdf(
        page,
        out_path=out_pdf,
        width_in=13.33, height_in=50.0,
        margin_in=0.3,
        inject_page_break_avoid=False,
    )
    page.emulate_media.assert_called_once_with(media="screen")
    page.pdf.assert_called_once()
    kwargs = page.pdf.call_args.kwargs
    assert kwargs["width"] == "13.33in"
    assert kwargs["height"] == "50.0in"
    assert kwargs["print_background"] is True
    assert kwargs["prefer_css_page_size"] is False
    assert kwargs["display_header_footer"] is False
    assert kwargs["margin"]["top"] == "0.3in"


def test_render_pdf_injects_page_break_css_for_paginated(tmp_path):
    page = MagicMock()
    render_pdf(
        page, out_path=tmp_path / "x.pdf",
        width_in=8.5, height_in=11.0, margin_in=0.3,
        inject_page_break_avoid=True,
    )
    page.add_style_tag.assert_called()
    css = page.add_style_tag.call_args.kwargs.get("content", "")
    assert "page-break-inside" in css or "break-inside" in css
