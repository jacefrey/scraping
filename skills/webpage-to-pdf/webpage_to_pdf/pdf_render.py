"""Playwright render helpers (spec §6.3, §6.5, §6.6)."""
from __future__ import annotations
import time
from pathlib import Path
from typing import Any


_SCROLL_HEIGHT_PROBE = "document.documentElement.scrollHeight"

_FLATTEN_STICKY_JS = """
(() => {
  for (const el of document.querySelectorAll('*')) {
    const s = window.getComputedStyle(el);
    if (s.position === 'fixed' || s.position === 'sticky') {
      el.dataset.originalPosition = s.position;
      el.style.position = 'static';
    }
  }
})();
"""

_HIDE_FIXED_JS = """
(() => {
  for (const el of document.querySelectorAll('*')) {
    const s = window.getComputedStyle(el);
    if (s.position === 'fixed' || s.position === 'sticky') {
      el.dataset.originalPosition = s.position;
      el.style.display = 'none';
    }
  }
})();
"""

_PAGE_BREAK_CSS = """
p, li, blockquote, pre, td, h1, h2, h3, h4, h5, h6, figure {
  page-break-inside: avoid;
  break-inside: avoid;
}
"""


def run_lazy_load_loop(page, cfg: dict[str, Any]) -> int:
    """Incremental scroll loop until content height stabilizes (spec §6.5).

    Returns the step count.
    """
    ll = cfg["render"]["lazy_load"]
    max_steps = int(ll["max_scroll_steps"])
    max_seconds = float(ll["max_scroll_seconds"])
    pause_ms = float(ll["scroll_pause_ms"])
    layout_settle_ms = float(ll["layout_settle_ms"])

    last_height: int | None = None
    stable_count = 0
    steps = 0
    start = time.monotonic()
    while stable_count < 2 and steps < max_steps and (time.monotonic() - start) < max_seconds:
        page.evaluate("window.scrollBy(0, window.innerHeight * 0.8);")
        time.sleep(pause_ms / 1000.0)
        h = page.evaluate(_SCROLL_HEIGHT_PROBE)
        if last_height is not None and h == last_height:
            stable_count += 1
        else:
            stable_count = 0
        last_height = h
        steps += 1

    page.evaluate("window.scrollTo(0, 0);")
    time.sleep(layout_settle_ms / 1000.0)
    return steps


def flatten_sticky_elements(page) -> None:
    """Spec §6.6: getComputedStyle walk; convert position:fixed/sticky → static."""
    page.evaluate(_FLATTEN_STICKY_JS)


def hide_fixed_elements(page) -> None:
    """Spec §6.6: alternative to flatten — display:none on fixed/sticky."""
    page.evaluate(_HIDE_FIXED_JS)


def render_pdf(
    page,
    *,
    out_path: Path,
    width_in: float,
    height_in: float,
    margin_in: float,
    inject_page_break_avoid: bool,
) -> None:
    """Apply `media="screen"`, optional page-break CSS, and call page.pdf().

    Spec §6.3: media="screen" is load-bearing.
    """
    page.emulate_media(media="screen")
    if inject_page_break_avoid:
        page.add_style_tag(content=_PAGE_BREAK_CSS)
    page.pdf(
        path=str(out_path),
        width=f"{width_in}in",
        height=f"{height_in}in",
        print_background=True,
        prefer_css_page_size=False,
        display_header_footer=False,
        margin={
            "top": f"{margin_in}in",
            "right": f"{margin_in}in",
            "bottom": f"{margin_in}in",
            "left": f"{margin_in}in",
        },
    )


def measure_scroll_height(page) -> int:
    """Spec §6.4 mechanics: documentElement.scrollHeight → fallback to body."""
    h = page.evaluate("document.documentElement.scrollHeight")
    if h == page.evaluate("document.documentElement.clientHeight"):
        h = page.evaluate("document.body.scrollHeight")
    return int(h)
