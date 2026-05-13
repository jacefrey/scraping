---
name: webpage-to-pdf
description: Convert a URL or local HTML file to PDF via Playwright print-to-PDF with screen media emulation, lazy-load scrolling, and sticky-element flattening. Supports live (double-fetch) and captured_html (DOM-stable) render modes. Returns a ConvertResult with the PDF path and metadata.
---

# webpage-to-pdf skill

URL → PDF via Playwright print-to-PDF with `screen` media emulation,
incremental lazy-load scrolling, and sticky-element flattening. Two
render modes: `live` (default, navigates to the original URL — high
visual fidelity) and `captured_html` (renders from saved HTML with
injected `<base href>` — DOM-stable, asset-contingent). PDF responses
are copied through as-is without re-render.

**Prerequisites:**
- python.org Python 3.12 at `/Library/Frameworks/Python.framework/Versions/3.12/`
- `beautifulsoup4` (`pip install --user beautifulsoup4`)
- `playwright` + Chromium (already installed for `web-fetch`):
  `pip install --user playwright && playwright install chromium`
- Sibling skill: **`web-fetch`** (delegated URL fetching). Install via
  the `scraping` plugin marketplace.

## §1 — When to use this skill

Reach for `webpage-to-pdf` when you need a visual-fidelity PDF of a
web page (web archive, debugging, share-link capture). The default
`page_format = "continuous"` produces a single tall page (no
pagination); use `Letter` / `A4` / `Legal` / `screen-paginated` for
printable output. Use `webpage-to-md` when you want Markdown text.

## §2 — Public API

```python
from webpage_to_pdf import convert, ConvertResult, ConvertError

result = convert(
    source="https://example.com/article",   # http(s):// URL, file:// URL, or Path
    output_dir=Path("out/"),
    output_stem=None,
    selector=None,                          # article-mode CSS selector (HTML only)
    page_format="continuous",               # or "screen", "Letter", "A4", "Legal",
                                            # "screen-paginated", or {"width": "...", "height": "..."}
    render_mode="live",                     # "live" | "captured_html"
    margin_in=0.3,
    flatten_sticky=None,                    # None=auto, True, False
    base_url=None,                          # explicit base for local HTML inputs
    cfg=None,
)
# result.pdf_path             → the produced PDF
# result.source_html_path     → persisted <stem>.html (None for PDF passthrough)
# result.rendered_html_path   → <stem>.rendered.html for live mode (None otherwise)
# result.render_mode          → "live" | "captured_html" | None (passthrough)
# result.live_double_fetch    → True only when render_mode="live"
# result.passthrough          → True when input was a PDF
```

## §3 — Configuration

Copy `webpage-to-pdf.toml.example` to your project root or
`~/.config/webpage-to-pdf.toml`. Precedence: explicit `cfg` > CWD > user > defaults.

Key knobs:
- `[render] render_mode` — `"live"` (default) or `"captured_html"`.
- `[render] flatten_sticky` — `"auto"` (default), `true`, or `false`.
- `[render] hide_fixed` — alternative to flatten (display:none); precedence wins over flatten.
- `[render] strip_selectors` — pre-render removal of cookie banners / chat widgets.
- `[render.lazy_load]` — `scroll_pause_ms`, `max_scroll_steps`, `max_scroll_seconds`, `layout_settle_ms`.
- `[render.viewport] width_px / height_px` — page geometry inputs (96 DPI assumed).

## §4 — Common traps

- **`live` mode double-fetches.** web-fetch GETs the URL, Playwright navigates to it again. Sites can return different content between the two fetches. Use `render_mode="captured_html"` when the saved HTML must be the source of truth.
- **`captured_html` mode is DOM-stable, not asset-stable.** External CSS/JS/images/fonts still load from the network at render time.
- **200" Adobe Reader cap.** `"continuous"` auto-falls-back to `"screen-paginated"` when content height > 200". Do NOT remove the cap — it's a viewer-compatibility constraint.
- **`media="screen"` is load-bearing.** Without it, Playwright uses print media and strips navigation. The skill always sets it (spec §6.3).
- **Sticky-element handling precedence:** `strip_selectors` first → `hide_fixed` if set → `flatten_sticky` otherwise.
- **Source HTML invariant.** Persisted `<stem>.html` is the bytes returned by `web-fetch`, untouched.

## §5 — Regression checks when updating this skill

```bash
cd ~/.claude/skills/webpage-to-pdf
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v -m "not integration"
```

All unit tests mock the Playwright `sync_playwright()` context manager
so the suite runs in <5 seconds and never launches a browser. Live
smoke test (network + real Chromium, ~15 seconds):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v -m integration
```
