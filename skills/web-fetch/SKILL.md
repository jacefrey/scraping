# web-fetch skill

URL → bytes with HTTP→Playwright auto-fallback. The single network primitive
underneath the rest of the `scraping` plugin (`webpage-to-md`, `webpage-to-pdf`,
and direct consumers).

**Prerequisites:**

- python.org Python 3.12 at `/Library/Frameworks/Python.framework/Versions/3.12/`
- `requests` (`pip install --user requests`)
- `playwright` + Chromium (`pip install --user playwright && playwright install chromium`)

The plugin's `apify-runner` skill is stdlib-only and does NOT require these.

## §1 — When to use this skill

Reach for `web-fetch` when you need raw bytes from a URL with provenance:
content hash, redirect chain, fetch method, content-type with source attribution.
Use `webpage-to-md` (Phase B) or `webpage-to-pdf` (Phase B) instead when you
want converted output; they delegate to this skill internally.

For sites that block ordinary public HTTP/JS-rendered access (LinkedIn,
Twitter/X, enterprise sites with TLS/JA3 fingerprinting, behavioral challenges),
use `apify-runner` instead — that's a paid third-party lane.

## §2 — Public API

```python
from webfetch import fetch, FetchResult, FetchError

result = fetch(
    "https://example.com/article",
    fetch_method="auto",              # "auto" (default) | "http" | "playwright"
    return_blocked_content=False,     # surface bot_challenge / auth_required
                                      #   as a partial result instead of raising
    if_none_match=None,               # ETag — accepted-but-ignored in MVP
    if_modified_since=None,           # HTTP-date — accepted-but-ignored in MVP
    cfg=None,                         # optional config dict; see §3
)
```

### Routing precedence

`auto` mode runs the §4.2 ladder: HEAD → URL suffix / HEAD content-type →
GET → magic-byte peek → challenge detection → thin-shell heuristic →
Playwright fallback. Explicit `fetch_method="http"` or `"playwright"` skips
the ladder. Per-domain overrides in `cfg["fetch"]["domain_overrides"]` apply
ONLY when `fetch_method == "auto"`. An explicit caller choice always wins.

### `FetchResult` fields

See `docs/superpowers/specs/2026-05-03-scraping-design.md` §4.1 (inside the
plugin repo). Key fields:

- `requested_url`, `final_url`, `redirect_chain` — provenance
- `content` (bytes), `content_type`, `content_type_source`, `encoding`
- `content_length_bytes`, `content_hash_sha256` — integrity
- `http_status`, `fetch_method`, `error_category`, `headers`
- `etag`, `last_modified`, `not_modified` — conditional-GET signals
- `playwright_details` — populated only when `fetch_method == "playwright"`

### `FetchError.error_category`

One of: `network`, `timeout`, `auth_required`, `blocked`, `not_found`,
`rate_limit`, `legal_restriction`, `server_error`, `bot_challenge`,
`redirect_loop`, `playwright_unavailable`, `response_too_large`,
`decoded_body_too_large`, `html_parse_safety`.

Pass `return_blocked_content=True` to convert `bot_challenge`,
`auth_required`, and `blocked` into a partial `FetchResult` (with
`error_category` set and `content` populated) instead of raising.

## §3 — Configuration

Copy `web-fetch.toml.example` to your project's CWD or `~/.config/web-fetch.toml`
and edit. Precedence: explicit `toml_path` arg to `load_config()` > `CWD/web-fetch.toml` >
`~/.config/web-fetch.toml` > baked defaults.

Or pass an in-memory `cfg` dict directly to `fetch()`.

## §4 — Common traps

- **`networkidle` timeouts on analytics-heavy sites.** Modern pages with
  ads, long-polling, or websockets never reach `networkidle`. Use a per-domain
  override with `wait_for = "domcontentloaded"` plus a `wait_for_selector`
  pointing at the article body.
- **HEAD blocked by some servers.** `use_head = false` disables HEAD pre-flight.
- **Magic-byte detection produces a single fetch only.** A body that doesn't
  start with `b"%PDF"` is treated as HTML; the request is NOT re-fetched.
- **Challenge detection is conservative.** False positives are possible
  (especially on pages that mention "verifying you are human" in their
  prose). Pass `return_blocked_content=True` to inspect the body that was
  flagged. Custom challenge frameworks (Imperva, etc.) can be added via
  `cfg["fetch"]["detection"]["challenge_markers"]`.
- **Per-process politeness.** `min_delay_ms_per_host` enforces a delay
  BETWEEN fetches to the same host within a single process. Multi-process
  bulk callers must coordinate cross-process rate limits externally.
- **`return_blocked_content=True` mutates the dispatched cfg only**, NOT
  the caller's cfg dict — safe to reuse a cfg across calls.

## §5 — Regression checks when updating this skill

```bash
cd ~/.claude/skills/web-fetch
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    -m pytest tests/ -v -m "not integration"
```

All unit tests must stay green. Run integration tests (`-m integration`)
manually before shipping changes that touch the HTTP or Playwright paths:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    -m pytest tests/ -v -m integration
```
