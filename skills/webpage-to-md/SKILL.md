---
name: webpage-to-md
description: Convert a URL or local HTML file to Markdown with persisted source HTML and YAML provenance frontmatter. Sits on top of web-fetch; returns a ConvertResult with the .md path, .html path, and a JSONL manifest row.
---

# webpage-to-md skill

URL → Markdown via `markdownify`. Persists the source HTML alongside the
derived Markdown, emits a YAML frontmatter block with full fetch
provenance, and supports a local-path fast path for iterate-without-
re-fetching workflows.

**Prerequisites:**
- python.org Python 3.12 at `/Library/Frameworks/Python.framework/Versions/3.12/`
- `beautifulsoup4` (`pip install --user beautifulsoup4`)
- `markdownify` (`pip install --user markdownify`)
- `pyyaml` (`pip install --user pyyaml`)
- Sibling skill: **`web-fetch`** (depends on it for the URL path). Install via
  the `scraping` plugin marketplace (`claude plugin install scraping@scraping`)
  or symlink at `~/.claude/skills/web-fetch/`.

## §1 — When to use this skill

Reach for `webpage-to-md` when you need a Markdown document from a public
URL, with the source HTML preserved alongside for reproducibility. The
default mode persists `<stem>.html`, `<stem>.html.meta.json` (sidecar),
and `<stem>.md`, plus appends one row to `manifest.jsonl` per attempt.
Use `webpage-to-pdf` when you need visual fidelity.

## §2 — Public API

```python
from webpage_to_md import convert, ConvertResult, ConvertError, ConvertConfigError

result = convert(
    source="https://example.com/article",   # http(s):// URL, file:// URL, or local Path
    output_dir=Path("out/"),
    selector=None,                          # CSS selector to narrow before MD conversion
    output_stem=None,                        # override the filename stem
    emit_frontmatter=True,                   # YAML provenance block at the top
    cfg=None,
)

# result.md_generated -> True for HTML; False for PDF responses (v0.1)
# result.markdown_path -> Path to the .md (None when the response was a PDF)
# result.source_path   -> Path to <stem>.html (None for PDF responses)
# result.pdf_path      -> Path to <stem>.pdf (set when the response was a PDF)
```

## §3 — Configuration

Copy `webpage-to-md.toml.example` to your project root or
`~/.config/webpage-to-md.toml`. Precedence: explicit `cfg` argument >
`CWD/webpage-to-md.toml` > `~/.config/webpage-to-md.toml` > baked defaults.

Key knobs:

- `[convert.extraction] strategy` — `"selector_then_body"` (default) or
  `"selector_then_readability_then_body"` (raises `ConvertConfigError`
  until Readify ships).
- `[convert.html_to_md] strip_classes` / `strip_selectors` /
  `preserve_classes` — drop CTA / newsletter / cookie-banner noise.
- `[convert.html_to_md] heading_style` — `"ATX"` (default) or `"SETEXT"`.

## §4 — Common traps

- **PDF passthrough is v0.1 only.** When `web-fetch` returns
  `application/pdf`, the skill saves `<stem>.pdf` and returns
  `ConvertResult(md_generated=False)`. It does NOT invoke `pdf-to-markdown`;
  that cross-skill integration is reserved for v0.2 (see spec §5.9 callout).
- **Source HTML invariant.** The persisted `<stem>.html` is the bytes
  returned by `web-fetch`, untouched. URL normalization, content
  selection, and markdownify all operate on a working copy. Re-converting
  the saved HTML produces the same MD modulo `re_converted_at`.
- **Sidecar preserves provenance for local re-runs.** The first fetch
  writes `<stem>.html.meta.json` next to the HTML. Re-converting the
  local file with `convert(Path(...), ...)` reads the sidecar and emits
  frontmatter that preserves `url`, `final_url`, and
  `original_fetched_at`, plus a fresh `re_converted_at`.
- **`<base href>` wins over `final_url`** for relative URL resolution
  (HTML5 spec behavior). Sites that host content from one URL but resolve
  assets against another use this — bypassing the precedence breaks
  CDN-pathed images.
- **`markdownify` collapses colspan/rowspan in tables.** Source HTML with
  `<th colspan="2">` will render with the spanned cell appearing once and
  the row column count mismatching.
- **Readability strategy fails as a config error**, not
  `NotImplementedError`. The hook exists so Readify can plug in later
  without restructuring this skill.

## §5 — Regression checks when updating this skill

```bash
cd ~/.claude/skills/webpage-to-md
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v -m "not integration"
```

All tests are mocked (no live network). The suite runs in <5 seconds.
Live smoke test (requires network):

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v -m integration
```
