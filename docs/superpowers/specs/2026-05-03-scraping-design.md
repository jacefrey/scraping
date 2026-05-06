# Web-Scraping Skills — Design Spec

**Captured:** 2026-05-03 from a brainstorming session
**Revised:** 2026-05-04 across four review waves (3 independent reviewers per wave, 12 reports total). See §12 for the resolved questions and which proposed changes were accepted, partial, or rejected with reasoning.
**Status:** Designed, not yet implemented
**Owner:** machine-manager
**Source:** Cross-project audit identified four scraping-adjacent G3 factoring candidates (Profisee × 4, linkedin × 1) plus AAA-radio's Selenium scraper as a third consumer; this spec extracts and generalizes them into a coherent skill family.

---

## 1. Context

Three projects on this machine currently do web scraping in three different ways:

| Project | Approach | Modules |
|---|---|---|
| **Profisee** | DIY: `requests` + BeautifulSoup + `playwright` | `scrape.py` (383 L), `scrape_blog.py`, `scrape_inventory.py`, `submit_forms.py` |
| **linkedin** | Third-party API (Apify) | `scripts/_apify.py` (149 L), `scripts/scrape_profiles.py`, `scripts/search_profiles.py` |
| **AAA-radio** | Selenium headless Chrome | `src/triple_a_playlist_ops/fetch_chart.py` (341 L) |

Plus `ref-data` (greenfield) is a likely fourth consumer.

The G3 factoring rule from `project_registry_bootstrapped.md` ("≥2 consumers justifies extraction") is met for the network primitive and exceeded for the HTML->Markdown converter. None of the existing code is bad — it's just unshared. Without extraction, every new project re-invents one of these three approaches and accumulates more drift.

The two paradigms (DIY vs Apify) reflect a real architectural choice that the skill family preserves rather than collapses:

- **DIY** works for sites where ordinary public HTTP/JS rendering is sufficient (most of the open web). Cheap, fast, full control.
- **Apify** may be considered for sites that block ordinary public access (LinkedIn, Twitter/X, Instagram, enterprise sites with TLS/JA3 fingerprinting or behavioral challenges). Pay-per-request third-party. Using it does not grant rights the consumer doesn't already have (§1.5); the separation between lanes does, however, prevent accidental drift of the DIY skill toward circumvention.

The skill family ships **both** paradigms as separate skills; the caller picks based on the target site.

---

## 1.5. Scraping boundaries

The skills in this family **do not** circumvent technical access controls. They are designed for ordinary HTTP fetching and JS-rendered page conversion — what a logged-out user could reasonably retrieve from a public URL. The phrase "render fallback heuristics" used elsewhere in this spec refers strictly to **detecting when a page requires JavaScript execution to produce its visible content**, not to defeating bot challenges or fingerprinting protections.

**Non-goals (concise, impossible to miss):**

This skill family does not implement, and will not be extended to implement, **stealth browser fingerprinting, CAPTCHA solving, credential replay, TLS/JA3 impersonation, or anti-bot evasion**. Sites that block at those layers should be addressed by `apify-runner` (paid third-party) or, if that's also inappropriate, manual triage — not by adding evasion code here.

**Operating constraints for any consumer of these skills:**

- **No bypass of authentication, paywalls, CAPTCHAs, or other technical access controls.** When a fetch encounters one, the skill returns an error with the appropriate category (e.g. `auth_required`, `blocked`, `bot_challenge`); the caller decides what to do. Specifically, **a Cloudflare/DataDome/PerimeterX challenge page in the HTTP response triggers `error_category = "bot_challenge"`, NOT a Playwright fallback** (§4.2). Playwright is for JavaScript rendering, not challenge bypass.
- **`robots.txt` is the consumer's responsibility, but consumers should document their position.** The skill provides the network primitive; the calling project decides whether and how to honor `robots.txt` for the specific scrape it's running. Each consumer project should record one of the following in its CLAUDE.md (or scraping-specific doc): "respects robots.txt by default", "ignores robots.txt with rationale: …", or "robots.txt not applicable to this scrape because …". Without that record, the boundary is easy to skip in practice.
- **Conservative rate limits by default.** `web-fetch` ships with `min_delay_ms = 500` between fetches **to the same host within a single process** and respects `Retry-After` headers on 429/503. Per-process scope means concurrent processes against the same domain do not inherit each other's delays — multi-process bulk callers must coordinate domain-level rate limits externally.
- **Provenance is preserved on every fetch.** `requested_url`, `final_url`, `fetched_at`, content hash, redirect chain, and `content_type_source` are recorded on every result so any output is auditable back to its source.
- **Personal data from authenticated sites requires explicit project approval.** The Apify runner pattern doesn't change this — paying a third party to scrape behind authentication has the same legal and contractual obligations as doing it yourself.
- **`apify-runner` does not remove obligations.** It is a paid third-party invocation layer; using an Apify actor against a site does not grant rights the consumer doesn't already have.

These constraints belong in this spec because the same architectural decisions that enable legitimate scraping (Playwright fallback, retry policy, browser-compatible defaults) can shade into circumvention if applied carelessly. Documenting the line up front keeps the project on the right side of intent.

---

## 2. Goals

1. **Single network primitive.** One skill (`web-fetch`) owns all the messy logic of HTTP fetch, render-fallback detection, blocked-response categorization, content-type sniffing, retry policy, and per-host politeness. Bug fixes there propagate to every consumer.

2. **Composable converters.** Two higher-level skills layer on top: `webpage-to-md` (URL -> Markdown) and `webpage-to-pdf` (URL -> PDF file). Both auto-detect PDF-vs-HTML inputs and route appropriately.

3. **Source preservation by default.** Every conversion persists the source artifact (HTML or PDF) alongside the derived output. Re-running extraction without re-fetching is a first-class workflow.

4. **Third-party paradigm available but optional.** `apify-runner` provides a stdlib-only generic Apify actor invocation client. Projects that don't need it pay zero cost (no extra deps).

5. **Carefully migrated consumers.** AAA-radio's weekly automation, linkedin's deliverable-complete code, and Profisee's deferred archive each get an explicit migration playbook with safety gates.

---

## 3. Architecture overview

Four skills, layered:

```
   ┌──────────────────────┐    ┌──────────────────────┐
   │   webpage-to-md      │    │   webpage-to-pdf     │
   │   (URL -> Markdown)  │    │   (URL -> PDF file)  │
   └──────────┬───────────┘    └──────────┬───────────┘
              │                            │
              ├────────┬───────────────────┤
              ↓        ↓                   ↓
         ┌──────────────────────────┐    ┌──────────────────────┐
         │       web-fetch          │    │  pdf-to-markdown     │
         │  URL -> bytes + metadata │    │  (existing skill)    │
         │  HTTP/Playwright         │    └──────────────────────┘
         │  render fallback         │
         └──────────────────────────┘

   ┌──────────────────────┐
   │   apify-runner       │   Stands alone — third-party API client.
   │   actor + input ->   │   Different execution lane; no code dependency
   │   dataset            │   on the DIY trio above. Used when the open-web
   │                      │   lane explicitly cannot reach a target.
   └──────────────────────┘
```

**Two principles:**

1. **`web-fetch` is the only place that knows network code.** Both higher-level skills delegate fetching to it. Retry policy, content-type sniffing, render-fallback detection, blocked-response categorization, per-host politeness — all live there.

2. **Cross-skill imports use a shared helper.** Each consumer skill ships a `skill_imports.py` module (`use()` + `validate_imported()`) that resolves sibling skills via the canonical `~/.claude/skills/` layout and validates the imported module's `__file__` is under the expected skill directory. See §8.1 for the canonical pattern; never inline `Path(__file__).resolve().parents[2]` walks at the call site.

**Implication for Readify:** the existing Readify backlog item ("URL -> canonical Markdown artifact with Header + Body + System Record JSON") becomes a thin wrapper around `webpage-to-md` plus a provenance/audit metadata layer. Readify's effort drops from "multi-session greenfield" to "one focused session, build the Header/JSON layer on top of webpage-to-md." Worth keeping on backlog as a follow-on.

---

## 4. `web-fetch` — the foundation

### 4.1 Public API

```python
from webfetch import fetch, FetchResult, FetchError

result = fetch(
    "https://example.com/article",
    *,
    fetch_method="auto",              # "auto" (default) | "http" | "playwright"
    return_blocked_content=False,     # if True, surface bot_challenge/auth_required as a partial result instead of raising (§4.3)
    if_none_match=None,               # ETag — accepted-but-ignored in MVP; reserved for v0.2 conditional GET (see §4.4)
    if_modified_since=None,           # HTTP-date — accepted-but-ignored in MVP; reserved for v0.2 (see §4.4)
    cfg=None,
)

# --- Identity + provenance ---
result.requested_url          # what the caller asked for
result.final_url              # final URL after redirect chain
result.redirect_chain         # list[str] of intermediate URLs (empty if no redirect)
result.started_at             # UTC datetime when the fetch began
result.completed_at           # UTC datetime when the fetch finished
result.fetched_at             # alias of completed_at, kept for compatibility

# --- Content ---
result.content                # bytes — body as decoded (gzip/deflate auto-decoded by requests)
result.content_type           # "text/html" | "application/pdf" | "image/..."
result.content_type_source    # "head" | "get_header" | "magic_bytes" | "url_suffix" | "playwright_render"
result.encoding               # str | None — charset from Content-Type or BOM; None for binary
result.content_length_bytes   # int — len(content) on the decoded body
result.content_hash_sha256    # hex digest of `content` (decoded body bytes — see §4.4 on compression)

# --- Network metadata ---
result.http_status            # 200, 404, etc.
result.fetch_method           # "http" | "playwright" — what was actually used
result.error_category         # None on success; see §4.3 for the partial-success cases
result.duration_ms            # convenience: (completed_at - started_at).total_seconds() * 1000
result.headers                # response headers (lowercased keys)

# --- Conditional-GET response signals (populated opportunistically; conditional-GET behavior is v0.2) ---
result.etag                   # str | None — from response ETag header
result.last_modified          # str | None — from response Last-Modified header
result.not_modified           # bool — always False in MVP; reserved for 304 responses in v0.2 (see §4.4)

# --- Render-path detail (None when fetch_method == "http") ---
result.playwright_details     # dict: wait_strategy, wait_for_selector, scroll_passes, redirect_count, ...
```

**Playwright result encoding.** When `fetch_method == "playwright"`, the rendered HTML is obtained via `page.content()` (which returns a Python `str`), then encoded to UTF-8 bytes before being assigned to `result.content`. `result.encoding = "utf-8"` and `result.content_hash_sha256` is computed over those UTF-8 bytes. `result.content_type` is set to `"text/html; charset=utf-8"` with `content_type_source = "playwright_render"`. This keeps the byte-oriented `FetchResult` contract uniform across HTTP and Playwright paths.

**`fetch_method` precedence.** When the caller passes `fetch_method != "auto"`, that explicit choice **wins over per-domain overrides**. Resolution order (highest priority first): explicit `fetch_method` argument -> `[[fetch.domain_overrides]]` matching the host -> auto heuristic ladder. Domain overrides exist to bias the auto path; they don't override an explicit caller decision.

**Unified redirect_chain.** `result.redirect_chain` records both HTTP-level redirects (from the `requests` redirect history) and any subsequent frame/browser navigations from Playwright, in chronological order. A page that 301s twice over HTTP and then JS-navigates once via `location.href` will have all three URLs in the chain, allowing audit consumers to see the full provenance regardless of which path was used.

**`fetch_method` parameter:**
- `"auto"` (default): full ladder per §4.2 — HEAD -> PDF detect -> HTTP -> render-fallback heuristic -> Playwright.
- `"http"`: use `requests` only. Skip Playwright even if HTML looks thin. Useful when caller knows the site is server-rendered.
- `"playwright"`: skip HTTP, go straight to Playwright. Useful for sites known to need rendering.

`fetch()` raises `FetchError` on terminal failure. Caller handles persistence — `web-fetch` never writes to disk.

**Partial-success vs terminal-failure semantics (see §4.3 for full table):**

| Outcome | `result` returned? | `error_category` | When |
|---|---|---|---|
| **Success** | Yes | `None` | 2xx response with usable content |
| **Partial: blocked content surfaced** | Yes | non-`None` | Caller passed `return_blocked_content=True` AND fetch hit `bot_challenge`/`auth_required`. Lets caller inspect challenge HTML for debugging. |
| **Success: PDF/binary** | Yes | `None` | Non-HTML payload returned as bytes — successful fetch, just not HTML |
| **Terminal failure** | No — `raise FetchError` | set on exception | All other error categories |

### 4.2 Render fallback heuristics + routing logic

**Note on terminology:** the heuristic ladder below decides *when a page needs JavaScript execution* (Playwright fallback) vs *when raw HTML is sufficient* (HTTP). This is a render-detection problem, not a circumvention problem. Bot-blocking signals are handled separately in §4.3 — they raise `bot_challenge` immediately rather than dropping into Playwright (because Playwright doesn't bypass anti-bot, see §1.5 non-goals).

**Cheapest-first ladder** (skipped entirely when caller passes `fetch_method="http"` or `"playwright"`):

1. **Per-domain override first.** If `web-fetch.toml` has `[[fetch.domain_overrides]]` matching the URL's host with `fetch_method = "http"` or `"playwright"`, skip the heuristic ladder and use the configured method. Escape hatch for sites where the heuristic consistently misfires.
2. **HEAD request** (if `use_head = true` — default) to get `Content-Type` cheaply. HEAD is treated only as a hint; never let a bad HEAD response poison the result. Servers that mishandle HEAD will get an automatic fall-through to GET; the toggle exists for sites that block HEAD entirely.
3. **PDF detection**:
   - If `Content-Type` (from HEAD or URL suffix) is `application/pdf`, OR URL path ends in `.pdf` -> fetch and return as PDF.
   - **Magic-byte fallback (streamed, single-fetch):** when content type is unknown, issue `requests.get(url, stream=True, timeout=magic_byte_peek_timeout_s)` (default `5 s`). Peek the first 1 KB. If it begins with `b'%PDF'` -> continue reading the same stream into a full download (treat as PDF). If not -> **continue reading the same response body into memory** (subject to `max_response_bytes` / `max_decoded_bytes` caps from `[fetch.parse_safety]`), then route as HTML in step 5. Do not issue a second GET. Aborting the stream and re-fetching loses request context and doubles network cost; reading the same body forward is cheaper and preserves a single redirect chain.
   - The peek timeout protects against slow servers that hang on the first chunk; on timeout, raise `FetchError(error_category="timeout")`.
   - Either path sets `content_type_source = "magic_bytes"` or `"url_suffix"` accordingly.
4. **Non-HTML binary** (image, zip, video, etc.): GET, return bytes. Done.
5. **HTML, blocked-response check FIRST.** Before any thin-shell analysis, run **challenge-page detection on the raw HTML response** (preserving `<script>` tags so JSON markers stay visible). If any of these are present:
   - Page `<title>` matches `Just a moment...`, `Access denied`, `Attention Required!`, `Verifying you are human`, `Please verify you are a human`.
   - HTML contains `cf-challenge-running`, `__cf_chl_jschl_tk__`, `cf-error-overview`, `Datadome`, `_pxhcaptcha`, or other known challenge framework markers.
   - HTTP status is 403 with a body that matches challenge fingerprints.
   
   -> set `error_category = "bot_challenge"`, do **not** invoke Playwright. Raise `FetchError("bot_challenge", ...)` unless the caller passed `return_blocked_content=True` (in which case return the partial `FetchResult` with the challenge HTML so the caller can inspect it). This is the correctness fix that aligns with §1.5: Playwright is for JS rendering, not challenge bypass.

6. **Render-fallback heuristic** (any of the following triggers Playwright fallback to render JS):
   - **Framework markers on raw HTML** (must be checked **before** tag-stripping, because these markers live inside `<script>` tags): `__NEXT_DATA__`, `__INITIAL_STATE__`, `id="__next"`, `id="root"` with empty body, `data-reactroot`, `<noscript>You need to enable JavaScript</noscript>`, `<script type="module">` without meaningful non-script body content.
   - **Text-content signal** (after stripping tags + scripts + styles): visible text < 200 chars while the raw HTML is non-trivial. Primary content-thinness signal.
   - **Byte-count signal** (secondary): HTTP body < `http_thin_threshold_bytes` (default 2 KB). Heavily-minified single-file React apps can be 300–500 KB of inline JSON + HTML and still need Playwright, so byte count alone is too coarse to lead with.
   
7. **Playwright fetch**: launch Chromium, navigate, wait per `wait_for` config (default `networkidle`; see §6.7-style note in §4.4 about noisy sites), optionally wait for `wait_for_selector`, return rendered HTML. Redirect-loop cap (default 20 frame navigations) raises `FetchError(error_category="redirect_loop")` rather than waiting for the timeout.

**Note on the order:** challenge detection (step 5) explicitly runs **before** thin-shell analysis (step 6). A page that's both blocked AND looks like an SPA shell should error as `bot_challenge`, not silently fall through to Playwright. Reverse-ordering would re-introduce the implicit-bypass concern §1.5 is trying to prevent.

### 4.3 Error handling and categories

`FetchError.error_category` (also set on `FetchResult.error_category` for partial-success cases) is one of:

| Category | Trigger | Retry policy | Default outcome |
|---|---|---|---|
| `network` | Connection refused, DNS failure, TLS handshake failure | 3 retries, exponential backoff (1s, 3s, 9s) | Raise after retries exhausted |
| `timeout` | HTTP path timeout exceeded `http_timeout_s` | **1 or 2 retries with backoff** (configurable; HTTP timeouts are often transient) | Raise after retries |
| `timeout` | Playwright path exceeded `playwright.timeout_s` | 1 retry | Raise after retry |
| `auth_required` | 401 | No retry | Raise (or return partial if `return_blocked_content=True`) |
| `blocked` | 403 (without challenge markers) | No retry | Raise (or return partial if `return_blocked_content=True`) — caller decides whether to try `apify-runner` |
| `not_found` | 404, 410 | No retry | Raise |
| `rate_limit` | 429 (also 408, 425) | Honor `Retry-After` up to `max_retry_after_s`; else exponential backoff | Raise after retries |
| `legal_restriction` | 451 | No retry | Raise |
| `server_error` | 5xx | 1 retry after 5 s | Raise |
| `bot_challenge` | HTTP response contained challenge-page markers (Cloudflare/DataDome/PerimeterX) at step 5 of §4.2, OR Playwright was forced via `fetch_method="playwright"` and rendered a challenge page | **No retry, no Playwright fallback** | Raise (or return partial if `return_blocked_content=True`). Playwright is not a challenge bypass — see §1.5. |
| `redirect_loop` | Redirect chain exceeded `max_redirects` (default 20) | No retry | Raise |
| `playwright_unavailable` | Playwright launch failed; browser not installed | No retry | Raise with install hint: `python3.12 -m pip install --user playwright && playwright install chromium` |
| `response_too_large` | Raw response bytes (pre-decompression) exceeded `max_response_bytes` from `[fetch.parse_safety]` | No retry | Raise — abort the GET; runaway responses are terminal |
| `decoded_body_too_large` | Post-gzip/deflate body exceeded `max_decoded_bytes` (compression-bomb guard) | No retry | Raise |
| `html_parse_safety` | Visible-text extraction during the thin-shell heuristic exceeded `max_html_text_chars` | No retry | Raise — parser-stage cap, distinct from network-stage caps above |

**`return_blocked_content` parameter** on `fetch()`: when `True`, instead of raising on `auth_required`, `blocked`, or `bot_challenge`, the function returns a partial `FetchResult` with `error_category` set and the response body in `result.content`. Useful for debugging — lets the caller inspect the challenge page without writing exception handlers everywhere. Default `False`.

**HTTP timeout retries** (revised from earlier draft): HTTP timeouts are often transient (transient packet loss, cold-cache origin server). Default `http_timeout_retries = 2` with exponential backoff (2 s, 6 s) before raising. Playwright timeouts default to `playwright_timeout_retries = 1` (the launch cost is high; aggressive retries waste resources). Both configurable; can be set to 0 to preserve the no-retry-on-timeout behavior for callers who want fail-fast.

Total timeout is configurable per path (`http_timeout_s`, `fetch.playwright.timeout_s`).

### 4.4 Configuration — `web-fetch.toml`

```toml
[fetch]
http_timeout_s = 10
http_thin_threshold_bytes = 2048
network_retries = 3                        # DNS / TLS / connection-refused failures only — does NOT cover timeouts (see http_timeout_retries below)
http_timeout_retries = 2                   # HTTP timeouts are often transient; retry 2x by default
use_head = true
head_timeout_s = 5
magic_byte_peek_timeout_s = 5              # see §4.2 step 3 — protects the streamed PDF-vs-HTML peek against hung servers
user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
max_redirects = 20
return_blocked_content = false             # default; per-call override available

[fetch.parse_safety]
max_response_bytes = 50_000_000            # raw bytes cap — raises `response_too_large` past this
max_decoded_bytes = 200_000_000            # post-gzip/deflate cap — raises `decoded_body_too_large` (compression bombs)
max_html_text_chars = 5_000_000            # parser-stage cap on visible text — raises `html_parse_safety`

[fetch.detection]
# Challenge-page markers used in §4.2 step 5. Internal defaults cover the
# big three (Cloudflare, DataDome, PerimeterX); per-domain or per-deployment
# additions belong here.
challenge_markers = []                     # extra markers appended to the built-in list; e.g. ["Imperva Incapsula"]

[fetch.politeness]
# Per-host politeness — each host has an independent delay timer.
# A 500 ms global delay would unnecessarily slow unrelated hosts; per-host
# delays do what's actually intended (don't hammer one site).
min_delay_ms_per_host = 500                # min interval BETWEEN fetches to the same host within a single process
respect_retry_after = true                 # honor Retry-After on 429/503
max_retry_after_s = 120                    # cap server-requested delay

# IMPORTANT: politeness is per-process. Multi-process bulk callers
# coordinate their own cross-process rate limits (shared lock, redis,
# or external scheduler) — that's out of scope for this skill.

[fetch.compression]
# requests auto-decodes gzip/deflate. content_hash_sha256 hashes the
# DECODED body that downstream converters see (not the wire bytes).
# A future `wire_hash_sha256` could be added if wire-level audit ever
# becomes a requirement; not now.

[fetch.playwright]
timeout_s = 30
playwright_timeout_retries = 1
wait_for = "networkidle"                   # or "domcontentloaded" / "load" — see note below
wait_for_selector = ""                     # optional CSS selector for stubborn JS-rendered content
extensions = []                            # FUTURE: paths to unpacked Chromium extensions
headless = true                            # auto-set False if extensions populated
max_redirects = 20                         # raise FetchError(redirect_loop) past this

# Note on `wait_for = "networkidle"`: networkidle waits for <500 ms of network
# silence, which never triggers on pages with continuous analytics, ads, or
# long-polling. For analytics-heavy sites, `domcontentloaded` + a `wait_for_selector`
# pointing at the article body is faster and more reliable. Default stays at
# networkidle for typical pages; per-domain override (below) handles noisy sites.

# Conditional GET reservation (v0.2 — accepted-but-ignored in MVP).
# In MVP, `fetch()` accepts `if_none_match=` / `if_modified_since=` arguments and ignores them.
# In v0.2, when populated and `[fetch.conditional_get].enabled = true`, web-fetch will:
#   - set `If-None-Match` / `If-Modified-Since` request headers
#   - on 304 response, return a FetchResult with:
#       result.http_status = 304
#       result.not_modified = True
#       result.content = b""
#       result.content_hash_sha256 = None
#       result.etag / result.last_modified populated from the 304 response
# Defining the future shape now keeps consumers' code stable across the upgrade.
# AAA-radio's weekly chart fetch is the obvious first consumer once implemented.
[fetch.conditional_get]
enabled = false

# Optional per-domain overrides. Each entry pins a host to a specific fetch method
# and skips the heuristic ladder for that domain. Useful when the heuristic
# misfires consistently for a known target.
# [[fetch.domain_overrides]]
# host = "example-spa.com"
# fetch_method = "playwright"
# wait_for = "domcontentloaded"
# wait_for_selector = ".main-article"
#
# [[fetch.domain_overrides]]
# host = "static-blog.com"
# fetch_method = "http"
```

**Config precedence** (highest priority first): explicit `toml_path` argument -> `CWD/web-fetch.toml` -> `~/.config/web-fetch.toml` -> baked defaults. Same precedence as the other skills in this family.

### 4.5 Dependencies

- `requests` (already installed on host)
- `playwright` + Chromium (`python3.12 -m pip install --user playwright && playwright install chromium`)
- python.org Python 3.12

### 4.6 File layout

```
~/.claude/skills/web-fetch/
  SKILL.md
  web-fetch.toml.example
  webfetch/
    __init__.py            # exports fetch, FetchResult, FetchError
    config.py
    detect.py              # content-type + thin-shell heuristics
    http.py                # requests-based fetch path
    playwright_fetch.py    # Playwright fallback path
  tests/
    test_webfetch.py
    fixtures/
      thin-shell.html
      sample.pdf
```

### 4.7 Future hook — browser extensions

The brainstorming session surfaced a real concern about Playwright + browser extensions (uBlock Origin, Ghostery, etc.). Approach:

- **MVP:** `extensions = []` config field exists but no implementation. `headless = true` always.
- **Future:** when populated, switches to `chromium.launch_persistent_context()` with `--load-extension` flags. Forces `headless=False` (Chromium limitation). One-time integration when a real consumer needs it.

---

## 5. `webpage-to-md` — URL -> Markdown

### 5.1 Public API

```python
from webpage_to_md import convert

md_path = convert(
    source="https://example.com/article",   # http(s):// URL, file:// URL, or local Path
    output_dir=Path("out/"),
    *,
    selector=None,                          # CSS selector to narrow before MD conversion (HTML only)
    output_stem=None,                        # override filename (default: derived from URL slug)
    emit_frontmatter=True,                   # YAML provenance block at the top
    cfg=None,
)
# Returns Path to <output_dir>/<stem>.md
```

### 5.2 Routing — URL inputs

This pseudocode reflects the actual module structure introduced in §5.6 (extraction stage), §5.5 (`markdownify`-based conversion), and §5.7 (URL normalization). Function names match the file layout in §5.12.

```python
from bs4 import BeautifulSoup
from .routing import resolve_source
from .extraction import select_content_node
from .html_to_md import convert_to_markdown
from .provenance import build_frontmatter, normalize_relative_urls, write_meta_sidecar
from .naming import derive_stem

result = web_fetch.fetch(url)
stem = output_stem or derive_stem(result.final_url)
config_sha256 = cfg.fingerprint()  # SHA-256 over the resolved config dict

if result.content_type.startswith("application/pdf"):
    out_pdf = output_dir / f"{stem}.pdf"
    out_pdf.write_bytes(result.content)                # PERSIST source PDF
    pdf_meta = pdf_to_markdown.process(                # cross-skill call (§5.9)
        out_pdf,
        output_dir=output_dir,
        merge_provenance=build_frontmatter_pdf(        # see §5.9 for the merged-frontmatter dict
            result=result,
            source_artifact=out_pdf.name,
            config_sha256=config_sha256,
        ),
    )
    return pdf_meta.markdown_path

elif result.content_type.startswith("text/html"):
    out_html = output_dir / f"{stem}.html"
    out_html.write_bytes(result.content)               # PERSIST source HTML, untouched
    write_meta_sidecar(                                # §5.3 sidecar — preserves fetch metadata for local re-conversion
        out_html.with_suffix(".html.meta.json"),
        result=result,
    )

    # All mutation happens on a working copy; the persisted file is the canonical source.
    working_soup = BeautifulSoup(result.content, "html.parser")
    working_soup = normalize_relative_urls(            # §5.7: <base href> > final_url > fail
        working_soup, base_url=result.final_url,
    )
    content_node = select_content_node(                # §5.6: explicit > readability > body
        working_soup, selector=selector, strategy=cfg.extraction.strategy,
    )
    md_body = convert_to_markdown(content_node, cfg)   # §5.5: markdownify wrapper

    out_md = output_dir / f"{stem}.md"
    if emit_frontmatter:
        md_body = build_frontmatter(
            result=result,
            source_artifact=out_html.name,
            derived_artifact=out_md.name,
            selector=selector,
            extraction_strategy=cfg.extraction.strategy,
            config_sha256=config_sha256,
        ) + md_body
    out_md.write_text(md_body)
    return out_md

else:
    raise ValueError(f"unsupported content type: {result.content_type}")
```

**Source preservation invariant:** the persisted `<stem>.html` is the bytes returned by `web-fetch`, untouched. URL normalization, content selection, and markdownify all operate on a `working_soup` copy. A future re-conversion run (§5.3 local input path) parses the saved file fresh and applies the same mutations. The source artifact is never modified after write.

### 5.3 Routing — local inputs

When `source` is a local `Path` or `file://` URL: skip `web-fetch` entirely. Read the file directly, parse, convert. No network.

Detection rule:
- `source` is a `Path` instance -> local.
- `source` is a `str` starting with `http://` or `https://` -> fetch via `web-fetch`.
- `source` is a `str` starting with `file://` -> strip scheme, treat as local Path.
- Any other `str` (absolute path, relative path, `~/...`) -> treat as local Path. Resolve with `Path(source).expanduser().resolve()`.

This unlocks the **iterate-without-re-fetching** workflow:

```python
# First run: fetches, persists HTML + MD, returns MD path
md_path = convert("https://example.com/article", output_dir=Path("out/"))

# Later debugging: skip the network entirely, re-derive MD from saved HTML
md_path = convert(Path("out/article.html"), output_dir=Path("out/"))
```

**Provenance preservation across re-runs.** The persisted source HTML is untouched — it cannot carry frontmatter. To keep fetch-time metadata available for local re-conversion, `webpage-to-md` writes a sidecar file `<stem>.html.meta.json` next to the source HTML on the original fetch. The sidecar holds only fields not derivable from the HTML itself: `url`, `final_url`, `fetched_at`, `fetch_method`, `http_status`, `content_type_source`, `etag`, `last_modified`, `redirect_chain`, `source_sha256`, `web-fetch_version`. On a local re-conversion, `webpage-to-md` reads the sidecar (if present) and emits frontmatter that preserves `url`, `final_url`, `original_fetched_at`, plus a fresh `re_converted_at`. If the sidecar is absent (HTML produced by some other path), frontmatter falls back to: `<link rel="canonical">` if present for `url`; otherwise the local file path; `original_fetched_at` is omitted; `re_converted_at` is set. The sidecar is plain JSON (stdlib only) and ~1 KB; it's the cheapest way to make local re-conversion provenance-equivalent to fresh fetches.

### 5.4 Frontmatter shape

```yaml
---
# Identity + source URL
url: https://example.com/article             # requested URL (caller's input)
final_url: https://example.com/article       # after redirects
canonical_url: https://example.com/article   # from <link rel="canonical"> if present
title: "Article Title"                        # from <title> or first <h1>
content_type: text/html                       # from web-fetch
content_type_source: get_header               # head | get_header | magic_bytes | url_suffix | playwright_render
http_status: 200

# When + how
started_at: 2026-05-03T10:29:59Z              # web-fetch fetch start
completed_at: 2026-05-03T10:30:00Z            # web-fetch fetch end
fetched_at: 2026-05-03T10:30:00Z              # alias of completed_at; kept for legacy readers
fetch_method: playwright                      # http | playwright | pdf-passthrough

# Artifact paths (relative to output_dir)
source_artifact: example-com__article__a1b2c3d4.html
derived_artifact: example-com__article__a1b2c3d4.md
source_sha256: 7e8b3f9c0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2  # 64-hex; from web-fetch's content_hash_sha256

# Conversion-time choices (so consumers can reproduce or diff)
selector: ".article-body"                     # null when default body fallback used
extraction_strategy: selector_then_body       # see §5.6
config_sha256: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4

# Converter identity
converter: webpage-to-md
converter_version: 0.1.0
manifest_schema_version: "1.0"                # frontmatter shape version (see §8.10)
---
```

The frontmatter is a **subset of the manifest row** (see §8.10) — it carries the consumer-relevant fields a downstream reader needs to interpret the MD file in isolation. The manifest is the full per-run accounting surface (one row per file, regardless of whether the file embeds frontmatter).

Re-conversion (local input) adds:

```yaml
original_fetched_at: 2026-05-03T10:30:00Z    # preserved if available in canonical-tagged HTML
re_converted_at: 2026-05-03T15:00:00Z
```

This is the provenance layer that **Readify** (when it ships) will extend with replay metadata, signature blocks, and audit-grade hashes of derived chunks.

### 5.5 HTML->MD engine — committed to `markdownify`

Engine: **`markdownify`** (`pip install markdownify`). Mature, actively maintained, handles nested lists, malformed HTML, character entity normalization. Adding one pip dep is not a meaningful cost for the value.

**Known `markdownify` limitation — `colspan` / `rowspan`:** `markdownify`'s GFM table support renders structure but **collapses spanned cells without marking the span**, producing rows with incorrect column counts when the source uses `colspan` or `rowspan`. For Profisee's blog corpus (mostly prose, simple tables) this is irrelevant. For consumers that expect to scrape colspan-bearing tables (financial statements, rate cards, comparison matrices), the regression suite **must** include a colspan fixture and assert that the limitation is detected — not silently producing wrong output.

**Regression assertions** (source-driven; the old Profisee converter is a reference fixture, not a golden authority): for each fixture in `tests/fixtures/profisee-style.html`, the test parses the source HTML and asserts on the `markdownify` output:

- **Heading parity:** every `<h1>`–`<h4>` in the source produces a corresponding `#`–`####` line in the MD. No heading lost.
- **Link parity:** every `<a href>` retained after `strip_classes` / `strip_selectors` becomes a `[text](url)` link with the absolute (post-§5.7-normalization) URL. No anchor lost.
- **List parity:** total bullet count and ordered-list count in the MD matches the retained `<ul>` / `<ol>` item counts.
- **Table parity** (when present): row count matches; column count matches **on rows without colspan**; rows with colspan are flagged in test output (not asserted-equal — markdownify's limitation is documented).
- **No CTA boilerplate:** specific class-stripped elements (per the `strip_classes` config) do not appear in the MD output.
- **Title present:** the page title (from `<title>` or first `<h1>`) appears in the MD body.
- **Per-fixture content assertions:** each fixture pins one expected H2, one expected paragraph, and one expected outbound link (text + href). These are spelled out per fixture in the test file so that a converter that drops body content fails loudly.

Profisee's `_node_to_md()` output is preserved as a side-by-side reference (`tests/fixtures/profisee-style.expected.md`) for diff inspection during regressions, but **assertions never compare against it directly** — a cleaner converter that strips boilerplate may diverge from the old output and still be correct. New Profisee blog posts can be added as fixtures over time; each fixture re-asserts the contract.

Project-specific stripping (CTAs, ad blocks, newsletter widgets) happens **before** conversion, via the selector parameter or via custom node-removal logic the caller can pass through config (`strip_classes`, `strip_selectors`).

### 5.6 Two-stage extraction pipeline (hook design; readability layer deferred)

The conversion pipeline has two stages:

1. **Select content node** — narrow the HTML to the article body before MD conversion.
2. **Convert selected node to Markdown** — apply `markdownify` to the chosen subtree.

Stage 1 has three strategies, tried in order:

| Strategy | Trigger | Implementation |
|---|---|---|
| **explicit_selector** | Caller passed `selector=...` | `soup.select_one(selector)` |
| **readability** | `extraction.strategy = "selector_then_readability_then_body"` and no explicit selector | **HOOK ONLY in MVP — not implemented.** Eventually delegates to a Readability/Trafilatura ensemble. Currently raises `ConvertConfigError("readability strategy requires Readify; not yet shipped")` if invoked. (Misconfiguration, not implementation crash — `ConvertConfigError` is a config-level user error class, not a generic `NotImplementedError`.) |
| **body_fallback** | Default | `soup.select_one("main") or soup.select_one("article") or soup.body` |

Config:

```toml
[convert.extraction]
strategy = "selector_then_body"               # MVP default — skip readability layer
# strategy = "selector_then_readability_then_body"  # FUTURE — when Readify lands
```

The readability layer's actual implementation lives in **Readify** (per §3 architecture note). `webpage-to-md` provides the hook so Readify can plug in cleanly without restructuring this skill later. Keeping it as a hook now means future-Readify is a wrapper that injects its own Stage 1 strategy, not a fork.

### 5.7 Relative URL normalization

Before MD conversion, relative URLs in the **working soup copy** (not the persisted source HTML — see §5.2 invariant) are rewritten to absolute URLs.

**Base URL precedence** (highest first, per HTML5 spec):

1. **`<base href="...">` tag in the source HTML** — when present, all relative URLs in the document resolve against this base, not the document URL. This is HTML5 spec behavior; sites use `<base>` to host content from one URL but resolve assets against another (CDN paths, deployment-prefix workarounds).
2. **`result.final_url` from `web-fetch`** — fallback when no `<base>` tag is present.
3. **Fail** — raise `ConvertError` only if both are missing (extremely rare; `final_url` is always populated by `web-fetch` on success).

**Attributes normalized** (Markdown-relevant only — the working soup is mutated for conversion; the persisted HTML stays untouched):

- `<a href="...">`
- `<img src="..." srcset="...">`  ← `srcset` parsing handles the `url 1x, url 2x` syntax; each URL gets normalized independently. Without this, modern responsive images become broken-image placeholders.
- `<source src="..." srcset="...">` (inside `<picture>` or `<video>`)
- `<iframe src="...">` (preserved as iframe in MD with normalized URL)

**Attributes deliberately NOT normalized** for `webpage-to-md`'s soup-mutation step:

- `<link href="...">` (stylesheets) — irrelevant for Markdown output. (`webpage-to-pdf` may want to preserve these; it operates on its own pipeline.)
- `<script src="...">` — also irrelevant for Markdown output.
- Attributes inside elements stripped by `strip_classes` / `strip_selectors` config — those nodes are removed before normalization runs.

Implementation: `urllib.parse.urljoin(base=resolved_base, url=relative_href)` for each retained attribute. For `srcset`, parse the comma-separated descriptor list, urljoin each URL, re-emit. **`data:` URLs in srcset are passed through unchanged** — naïve comma-splitting would break them (data URLs can contain commas in base64 payloads), so the parser detects `data:` prefixes and emits them verbatim. For non-`data:` entries, the comma-split-then-urljoin approach is sufficient for the responsive-image patterns Profisee, AAA-radio, and ref-data are likely to encounter; if a future consumer needs full RFC-compliant srcset parsing, swap in `markdownify`'s helper or a dedicated parser.

### 5.8 Filename collision policy

URL slugs collide constantly: `/about`, `/resources`, `/article`, query-string variants, same path across domains. Default stem policy:

```
<domain>__<path_slug>__<short_hash>
```

Example:
- `https://example.com/blog/post-title?utm=foo` -> `example-com__blog-post-title__a1b2c3d4`
- `https://other.com/blog/post-title` -> `other-com__blog-post-title__e5f6a7b8`

Where:
- `domain` is the host with dots replaced by hyphens (`example-com`)
- `path_slug` is the path slugified (lowercase, non-word -> hyphen, no leading/trailing hyphens)
- `short_hash` is 8 hex chars of `sha256(final_url + query_string)`

Caller-supplied `output_stem` overrides this entirely.

### 5.9 PDF passthrough behavior + provenance

When `web-fetch` reports `content_type == "application/pdf"`:

1. Write bytes to `output_dir/<stem>.pdf`. Source PDF preserved alongside the Markdown.
2. **Build the web-side provenance dict** from `web-fetch`'s result: `url`, `final_url`, `fetch_method`, `http_status`, `started_at`, `completed_at`, `source_sha256`, `content_type_source`, `redirect_chain`, `source_artifact`, `config_sha256`. No PDF parsing in `webpage-to-md`.
3. Cross-skill import `pdf_to_markdown.process()` with the saved PDF, same `output_dir`, and pass the dict via the new `merge_provenance` kwarg (see contract below). `pdf-to-markdown` already opens the PDF with PyMuPDF for its own pipeline; reusing that open lets it return PDF metadata (`pdf_title`, `pdf_author`, etc.) in the same call without `webpage-to-md` adding `pymupdf` as a direct dependency.
4. **`pdf-to-markdown` builds the merged frontmatter** internally: it merges the web-side dict from step 2 with the PDF-internal metadata it already extracts, prepends the result to the produced MD, and returns a small `PdfMdResult` with `markdown_path` and the final `frontmatter` dict. Example merged frontmatter:

   ```yaml
   ---
   url: https://example.com/whitepaper.pdf
   final_url: https://example.com/whitepaper.pdf
   content_type: application/pdf
   started_at: 2026-05-04T10:29:59Z
   completed_at: 2026-05-04T10:30:00Z
   fetched_at: 2026-05-04T10:30:00Z
   fetch_method: http
   http_status: 200
   source_artifact: example-com__whitepaper__a1b2c3d4.pdf
   source_sha256: 7e8b3f9c0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2
   derived_artifact: example-com__whitepaper__a1b2c3d4.md
   converter: webpage-to-md -> pdf-to-markdown
   converter_version: "0.1.0 / 0.5.2"          # respective versions of the two skills
   pdf_title: "Acme Industries 2026 Whitepaper"
   pdf_author: "Jane Doe, Acme Research"
   pdf_subject: "Industrial automation trends"
   pdf_producer: "Adobe PDF Library 17.0"
   pdf_creation_date: 2026-04-15T09:12:00Z
   manifest_schema_version: "1.0"
   ---
   ```

5. Return `pdf_meta.markdown_path` — the MD path `pdf-to-markdown` wrote.

**Cross-skill contract change (Phase B scope).** This integration adds a new kwarg to `pdf_to_markdown.process()`:

```python
def process(
    pdf_path: Path,
    output_dir: Path,
    *,
    merge_provenance: dict | None = None,   # NEW — when set, prepended to the MD frontmatter
    cfg=None,
) -> PdfMdResult: ...
```

When `merge_provenance` is `None` (default), `pdf-to-markdown` retains its existing frontmatter behavior. When a dict is provided, `pdf-to-markdown` merges its PDF-internal metadata on top (PDF fields take precedence on `title`, `author`, etc., to avoid stomping consumer-supplied web-side fields), prepends the result, and exposes the final dict on `PdfMdResult.frontmatter`. This change ships as part of Phase B and is recorded in the §9.2 implementation table — it is not optional.

`pdf-to-markdown` produces either `output_dir/<stem>-md/` (multi-chapter) or `<stem>.md` (single chapter; its existing finalize behavior). The merged-frontmatter shape lands in whichever file is produced.

Net: caller gets back a path to MD; `output_dir` contains both the source PDF and the derived Markdown; the MD's frontmatter records the full provenance chain (HTTP fetch -> PDF passthrough -> MD conversion) with both `web-fetch` and PDF-internal metadata. `webpage-to-md` does not depend on `pymupdf` directly — all PDF parsing stays inside `pdf-to-markdown`.

### 5.10 Configuration — `webpage-to-md.toml`

```toml
[convert]
emit_frontmatter = true
default_selector = ""                       # empty = use the §5.6 strategy ladder

[convert.extraction]
strategy = "selector_then_body"              # "selector_then_readability_then_body" when Readify ships

[convert.html_to_md]
strip_classes = ["ad", "newsletter-signup", "social-share"]   # CSS classes to drop before conversion
strip_selectors = []                          # arbitrary CSS selectors to drop (e.g., ".cookie-banner")
preserve_classes = []                         # CSS classes to KEEP even if matched by stripping rules
heading_style = "ATX"                         # markdownify option: "ATX" (#) or "SETEXT" (===)
```

### 5.11 Dependencies

- `web-fetch` (cross-skill via `skill_imports.use("web-fetch")`)
- `pdf-to-markdown` (cross-skill; only used when content is PDF). PyMuPDF/fitz lives there — `webpage-to-md` does not import fitz directly.
- `beautifulsoup4` (HTML parsing)
- `markdownify` (HTML to Markdown engine)
- `pyyaml` (frontmatter serialization — see §8.5)
- python.org Python 3.12

### 5.12 File layout

```
~/.claude/skills/webpage-to-md/
  SKILL.md
  webpage-to-md.toml.example
  webpage_to_md/
    __init__.py            # exports `convert`
    config.py
    extraction.py          # Stage 1: selector -> readability hook -> body fallback
    html_to_md.py          # Stage 2: markdownify wrapper + project-specific cleanup
    provenance.py          # frontmatter generation + URL normalization helpers
    routing.py             # PDF vs HTML branch + local-input handling
    naming.py              # filename collision policy (§5.8)
  tests/
    test_webpage_to_md.py
    fixtures/
      simple-blog.html
      profisee-style.html  # regression fixture: markdownify output ≥ Profisee converter on this input
      sample.pdf
```

Note: the `frontmatter.py` module is named `provenance.py` to avoid namespace collision with the `python-frontmatter` pip package if it's ever installed in the same environment.

---

## 6. `webpage-to-pdf` — URL -> PDF (visual fidelity)

### 6.1 Public API

```python
from webpage_to_pdf import convert

pdf_path = convert(
    source="https://example.com/article",   # http(s):// URL, file:// URL, or local Path
    output_dir=Path("out/"),
    *,
    output_stem=None,                       # override filename (default: §5.8 naming policy)
    selector=None,                          # CSS selector to render only this subtree (HTML only) — see §6.1a
    page_format="continuous",               # alias of "screen" — see §6.4
    render_mode="live",                     # "live" | "captured_html" — see §6.2
    margin_in=0.3,
    flatten_sticky=None,                    # None = auto (False for continuous, True for paginated)
    base_url=None,                          # explicit base for local-HTML rendering when canonical/sidecar absent (see §6.2)
    cfg=None,
)
# Returns Path to <output_dir>/<stem>.pdf
```

**Article-mode rendering — the optional `selector` parameter.** Mirrors §5.6's content-narrowing in `webpage-to-md`. When set, `webpage-to-pdf` injects CSS pre-render that hides everything outside the selector subtree:

```css
/* Only the matching element and its ancestors/descendants stay visible */
:not(.__wpdf_visible__) { display: none !important; }
.__wpdf_visible__ { display: revert; }
```

The skill walks the DOM, marks the selected node + its ancestors + all descendants with the `__wpdf_visible__` class, then injects the rule. Different mechanism from clipping (preserves font sizing, page formatting, internal layout). Use this when the consumer wants a clean article-body PDF without crafting an exhaustive `strip_selectors` list. Default `None` (whole page rendered).

The mutation happens on the working DOM only; the persisted `<stem>.html` is never altered (same invariant as §5.2).

### 6.2 Render modes — `live` vs `captured_html` vs (future) `snapshot`

URL inputs go through one of two render paths in MVP. A future `"snapshot"` mode is reserved for archive-grade reproducibility (asset mirroring) — see below.

| `render_mode` | What happens | Visual fidelity | Reproducibility |
|---|---|---|---|
| **`"live"`** (default) | After `web-fetch` saves the HTML, Playwright navigates to the **original URL again** for the PDF render — **two network round-trips** to the same URL. External CSS/JS/images/fonts load from their original sources. | High — looks like the live page. | **Limited.** The saved `<stem>.html` is **not necessarily what was rendered into the PDF.** Between the `web-fetch` GET and the Playwright navigation, the site can return different content (session token expired, query string nonce changed, A/B-test bucket flipped, simply changed). Recorded in the result as `live_double_fetch=True` with `source_html_sha256` (from web-fetch) and `rendered_at` + `render_url` (from Playwright). For source-matches-render guarantees, use `"captured_html"`. |
| **`"captured_html"`** | Playwright loads the **saved HTML as `file://`** for the PDF render. A `<base href="https://original.com/">` tag is injected into `<head>` so relative URLs resolve. External assets fetch from the network at render time unless cached. | Partial — works for sites that respect `<base>` and serve assets unchanged. Breaks on frameworks that hardcode absolute paths in JS, check `window.location`, or refuse to load with mismatched origin. | **Saved HTML DOM is reproducible** (always — it's a flat read from disk). **Rendered PDF is only reproducible if external assets remain available and unchanged.** Mark this expectation in result frontmatter with `render_mode = "captured_html"` and a note that the PDF is contingent on external asset availability. |
| **`"snapshot"`** (FUTURE — not in MVP) | Playwright captures HTML + all referenced assets (CSS, JS, images, fonts) as MHTML or HAR + asset mirror. PDF renders from the captured bundle, fully offline. | High and stable. | **True archive-grade.** Re-rendering from the bundle produces the same PDF regardless of network availability or upstream changes. Reserved as a future fourth mode for legal-record-class archival; out of scope for MVP. |

**Default is `"live"`** for the highest-fidelity primary use case (visual capture, share-link, fidelity-first PDF). The double-fetch limitation is documented honestly so consumers who need strict source/render correspondence know to switch modes. Use the term **"visual capture"** for live mode rather than "web archive" — live mode is not archive-reproducible; "archive-grade" is reserved for the future `snapshot` mode.

**`"captured_html"`** is the right choice when the consumer needs the saved HTML to be the source of truth for the **DOM** that was rendered — e.g., legal record, regulatory submission, or any "this exact HTML produced this PDF" claim. Note: the saved HTML is the source of the DOM, not the source of the visual page; the rendered PDF is still **subject to asset drift** (CSS/images/fonts loaded at render time from external origins), so the visual fidelity guarantee is "DOM-stable, asset-contingent" rather than fully reproducible. Future `"snapshot"` mode is the strict-archive answer.

Either way, the source HTML is **always saved** to `output_dir/<stem>.html` — that part doesn't change between modes. The `<base href>` injection in `captured_html` mode happens on a working copy; the persisted HTML remains untouched (same invariant as §5.2).

**Routing logic:**

Same `source` detection rule as `webpage-to-md` (§5.3): `Path` instance, `file://` URL, or non-`http(s)://` string -> local. Otherwise URL.

```python
if source_is_local(source):
    if source.suffix == ".pdf" or first_bytes(source, 4) == b"%PDF":
        copy_to(source, output_dir / f"{stem}.pdf")
        append_manifest_row(passthrough=True)              # PDF-passthrough writes manifest only; no frontmatter (PDFs don't carry YAML)
        return output_dir / f"{stem}.pdf"
    # else assume HTML — local input always uses captured_html mode (no original URL to navigate to)
    base = (
        base_url                                            # explicit caller arg
        or read_meta_sidecar(source.with_suffix(".html.meta.json"))  # §5.3 sidecar from a prior fetch
        or canonical_link_in(source)                        # <link rel="canonical">
        or warn_no_base_and_skip_injection()
    )
    working_html = inject_base_href(source, base)           # working copy ONLY; persisted source untouched
    apply_strip_and_sticky(working_html, cfg)               # all DOM mutations happen here
    page.goto(f"file://{working_html_tempfile}")
    render_pdf_to(output_dir / f"{stem}.pdf")

else:  # URL input
    result = web_fetch.fetch(source)
    if result.content_type.startswith("application/pdf"):
        (output_dir / f"{stem}.pdf").write_bytes(result.content)
        append_manifest_row(passthrough=True)              # PDF-passthrough writes manifest only
        return output_dir / f"{stem}.pdf"

    if not result.content_type.startswith("text/html"):
        raise ValueError(f"unsupported content type: {result.content_type}")

    (output_dir / f"{stem}.html").write_bytes(result.content)   # persist source HTML, untouched
    write_meta_sidecar(...)                                # §5.3 — same sidecar shape, written by webpage-to-pdf too

    if render_mode == "live":
        page.goto(result.final_url)
        rendered_html = page.content()                     # always captured for transparency
        if cfg.render.persist_rendered_html:               # default True for live mode
            (output_dir / f"{stem}.rendered.html").write_text(rendered_html, encoding="utf-8")
    else:  # captured_html
        working_html = inject_base_href(saved_html_path, result.final_url)
        page.goto(f"file://{working_html_tempfile}")

    apply_strip_and_sticky(page, cfg)
    render_pdf_to(output_dir / f"{stem}.pdf")
```

**Caveat for `captured_html` mode:** some frameworks ignore `<base>` and hardcode absolute paths or use `window.location` to construct asset URLs at runtime. For these sites, `captured_html` will produce broken-image PDFs. The mode is documented as "best-effort" — when in doubt, use `"live"`.

**Live-mode double-fetch transparency:** the result records `live_double_fetch = True`, plus `source_html_sha256` (the web-fetch GET) and `render_html_sha256` (what Playwright actually rendered, as UTF-8 bytes via `page.content()`). When `[render].persist_rendered_html = true` (default for `live` mode), the rendered HTML is also written to `<stem>.rendered.html` so the hash is inspectable, not just verifiable. Consumers can compare the two: equal hashes mean the site served identical content twice; unequal hashes flag a divergence the consumer might want to know about (audit failure, site change between fetches, dynamic personalization). The PDF manifest row records both hashes plus `rendered_html_artifact: "<stem>.rendered.html"` when persisted.

**Source-HTML invariant for `webpage-to-pdf`.** Same rule as §5.2: the persisted `<stem>.html` is the bytes returned by `web-fetch`, untouched. All DOM mutations — `<base href>` injection, `strip_selectors`, `flatten_sticky`/`hide_fixed`, article-mode `selector` masking — happen on a working copy or on the live `page` context, never on the saved file. A reader who opens `<stem>.html` later sees what the server returned, not what we rendered.

### 6.3 Visual fidelity — Playwright print-to-PDF options

```python
page.emulate_media(media="screen")        # CRITICAL — render screen view, NOT print stylesheet
# ... lazy-load handling (see 6.5) ...
page.pdf(
    width=...,                              # from page_format
    height=...,                             # from page_format
    print_background=True,                  # preserve background colors and images
    prefer_css_page_size=False,             # use our config, not page's @media print rules
    margin={"top": f"{margin_in}in", ...},
    display_header_footer=False,            # no browser-injected headers
)
```

`media="screen"` is the load-bearing line. Without it, Playwright defaults to `print` media — which strips navigation, hides ads, and applies print stylesheets. For "faithful visual capture" you want `screen` — what the user sees in the browser, rendered onto pages.

### 6.4 Page formats

| `page_format` | Dimensions | When to use | Pagination |
|---|---|---|---|
| **`"continuous"`** ← default (alias: `"screen"`) | 13.33" wide × full content height (single tall page) | Web archive, debugging, fidelity-first capture | None — single page |
| `"screen-paginated"` | 13.33" × 8.33" (laptop aspect) | Long pages where one ridiculously tall page is unwieldy | Multi-page, screen-shaped |
| `"Letter"` | 8.5" × 11" | Printable artifact (US) | Multi-page paper |
| `"A4"` | 8.27" × 11.69" | Printable artifact (RoW) | Multi-page paper |
| `"Legal"` | 8.5" × 14" | Long-form printable | Multi-page paper |
| `dict` like `{"width": "16in", "height": "auto"}` | Custom | Full control | Depends on `height` |

`"screen"` is accepted as an alias for `"continuous"` for backward compatibility and for callers who naturally reach for "screen" — the rename is to disambiguate from `media="screen"` (the screen-vs-print stylesheet emulation, §6.3) which is a different concept that controls *which CSS rules* render, not page geometry.

**`"continuous"` mechanics:**

1. Load page with viewport `1280 × 800` by default (1280 / 96 dpi = 13.33"). The viewport width is configurable via `viewport.width_px`.
2. Wait for `networkidle` + lazy-load scroll loop (see §6.5).
3. Measure `document.documentElement.scrollHeight` (returns pixels). If it equals `clientHeight`, fall back to `document.body.scrollHeight` (some pages have `overflow: hidden` on `<html>` that suppresses the outer measurement).
4. Convert to inches: `height_in = pixels / 96`.
5. Sanity cap at 200". **This is a *consumer-viewer* compatibility cap (Adobe Reader's hard page-height limit), not a browser/Playwright/PDF technical limit.** Chromium can emit taller PDFs without complaint, but Adobe Reader and many other viewers refuse to display pages over 200". The cap exists to ensure the produced PDF actually opens in common viewers. If the page exceeds 200", auto-fall-back to `"screen-paginated"` and emit a one-line log warning. (Anyone "fixing" this away because Chromium accepts it would silently break Adobe Reader compatibility — leave the cap.)
6. Call `page.pdf(width="13.33in", height=f"{height_in}in", print_background=True, ...)`.

**96 DPI assumption (caveat):** the px-to-inches conversion assumes the standard 96 DPI mapping. If `viewport.width_px` is changed substantially, the conversion is still 96 DPI — pages using viewport-relative units (`vw`, `vh`) will scale with the viewport, but the resulting PDF page dimensions still reflect the 96-DPI mapping of pixel measurements. Document this assumption in the config comments; consumers needing different DPI scaling should set `width` and `height` explicitly via the `dict` form.

For paginated formats (`Letter`, `A4`, `Legal`, `"screen-paginated"`), an additional CSS rule is injected before render to discourage element-level page breaks:

```css
p, li, blockquote, pre, td, h1, h2, h3, h4, h5, h6, figure {
  page-break-inside: avoid;       /* legacy paged-media property */
  break-inside: avoid;             /* modern fragmentation property — use both for cross-engine coverage */
}
```

Reduces single-line bisection across page boundaries. Off for `"continuous"` (no page breaks to begin with).

### 6.5 Lazy-load handling

A single scroll-to-bottom misses infinite-scroll pages and progressive image loading. The renderer uses an incremental scroll loop that stops when content height stabilizes:

```javascript
let lastHeight = document.documentElement.scrollHeight;   // start with the actual height, not 0
let stableCount = 0;
let steps = 0;
const maxSteps = cfg.lazy_load.max_scroll_steps;          // default 50
const startTime = Date.now();
const maxSeconds = cfg.lazy_load.max_scroll_seconds;      // default 30

while (stableCount < 2 && steps < maxSteps && (Date.now() - startTime) / 1000 < maxSeconds) {
  window.scrollBy(0, window.innerHeight * 0.8);
  await new Promise(r => setTimeout(r, cfg.lazy_load.scroll_pause_ms));    // default 800
  const h = document.documentElement.scrollHeight;
  if (h === lastHeight) stableCount += 1;
  else stableCount = 0;
  lastHeight = h;
  steps += 1;
}
window.scrollTo(0, 0);
await new Promise(r => setTimeout(r, cfg.lazy_load.layout_settle_ms));    // default 250 — let sticky/lazy elements reflow on return-to-top
```

The `max_scroll_steps` and `max_scroll_seconds` caps prevent infinite-scroll pages (Twitter feeds, news listings) from spinning forever. After the loop exits, **respect the configured `[render.wait].strategy`** rather than hardcoding `networkidle` — the same warning that applies to the initial wait (§4.4) applies post-scroll: analytics-heavy sites never reach `networkidle`. Implementation: re-run the configured wait strategy with a hard timeout fallback (`cfg.render.wait.timeout_s`, default 10s) before calling `page.pdf()`.

Without this, lazy-loaded images render as blank squares and infinite-feed sites get truncated at the top fold.

### 6.6 Sticky-element flattening

For paginated formats (`Letter`, `A4`, `Legal`, `screen-paginated`), the browser's print pipeline can repeat sticky headers/banners on every page. The mitigation is to convert `position: fixed`/`sticky` elements to `position: static` before render.

A CSS-attribute selector (`*[style*="position: fixed"]`) only catches inline styles — but most sites apply `position` via class-based CSS rules, which inline-style matching misses. Instead, use a JS walk over computed styles:

```javascript
// Run via page.evaluate() before page.pdf()
for (const el of document.querySelectorAll("*")) {
  const s = window.getComputedStyle(el);
  if (s.position === "fixed" || s.position === "sticky") {
    el.dataset.originalPosition = s.position;
    el.style.position = "static";
  }
}
```

This is more expensive (touches every element) but reliable for the pre-render cleanup case. The captured `dataset.originalPosition` lets a future reverse pass restore the layout if needed.

Default behavior — `flatten_sticky=None` resolves to:
- `False` for `"continuous"` (no page breaks -> no repeats -> not needed)
- `True` for paginated formats (`Letter`, `A4`, `Legal`, `"screen-paginated"`)

Caller can override either way via the parameter or config.

**Sticky flattening can damage layout** — converting `position: fixed` to `static` can push content down or duplicate sticky-nav contents into the document flow. For sites where flatten breaks layout, two alternatives:

- **`strip_selectors` (also added to `webpage-to-pdf`'s config)** — surgical removal. Pre-render, drop nodes matching CSS selectors entirely (e.g., `.cookie-banner`, `[data-cookie-consent]`, `header.sticky-nav`, `#chat-widget`). The element is gone from the rendered DOM rather than re-positioned. Cleaner result for cookie banners, chat widgets, sticky promo bars.
- **`hide_fixed = true`** — alternative behavior: instead of `position: static`, set `display: none` on `position: fixed`/`sticky` elements. Removes them from the visual rendering without altering surrounding layout. Trade-off: less faithful to "what the user sees" since sticky elements were visible on screen.

Recommended pattern: use `strip_selectors` for known-noise elements (cookie banners, chat), `flatten_sticky=True` for general sticky-nav handling on paginated formats, leave both off for `"continuous"`.

**Precedence when multiple sticky-handling options are set:**

1. `strip_selectors` is applied first — selected nodes are removed from the working DOM entirely. Anything matched here is gone before the sticky pass runs.
2. If `hide_fixed = True`: remaining `position: fixed` / `position: sticky` elements are set to `display: none`. `flatten_sticky` is ignored (mutually exclusive — `hide_fixed` is the stronger of the two).
3. Else if `flatten_sticky = True` (or `"auto"` resolves to True for a paginated format): remaining `position: fixed` / `position: sticky` elements are set to `position: static`.
4. Else: no sticky handling.

Documented so a config combining both `flatten_sticky=True` and `hide_fixed=True` has a defined outcome (hide wins) instead of order-of-iteration luck.

### 6.7 Configuration — `webpage-to-pdf.toml`

```toml
[render]
page_format = "continuous"       # alias "screen" accepted; see §6.4
render_mode = "live"              # "live" | "captured_html" — see §6.2
margin_in = 0.3
flatten_sticky = "auto"           # "auto" | true | false
hide_fixed = false                # alternative to flatten_sticky — display:none instead of position:static
                                  # precedence: strip_selectors -> hide_fixed -> flatten_sticky (see §6.6)
inject_page_break_avoid = "auto"  # "auto" (true for paginated, false for continuous) | true | false
persist_rendered_html = true      # for live mode: write <stem>.rendered.html so render_html_sha256 is inspectable
strip_selectors = []              # CSS selectors to remove pre-render (cookie banners, chat widgets)
                                  # e.g., [".cookie-banner", "[data-cookie-consent]", "#chat-widget"]

[render.viewport]
# Note: 96 DPI assumption is baked into the px-to-inches conversion.
# Changing width_px scales the capture but the resulting PDF page dimensions
# still reflect the 96-DPI mapping. See §6.4 caveat.
width_px = 1280                   # default 13.33" wide
height_px = 800                   # default 8.33" — used for non-continuous modes

[render.wait]
# `networkidle` (default) waits for <500 ms of network silence. Modern pages
# with continuous analytics, ads, long-polling, or websockets never reach
# networkidle and time out instead. For those sites, prefer
# `strategy = "domcontentloaded"` plus a `selector` pointing at the
# article body — faster and more reliable. Per-domain overrides in
# web-fetch.toml can pin specific hosts to the right wait strategy.
#
# Lifecycle scope: this [render.wait] block controls the PDF render pass
# (page-stable signal before `page.pdf()` and after the lazy-load loop).
# The fetch-time Playwright wait is configured separately in
# `web-fetch.toml [fetch.playwright]`. Different lifecycle stages — they
# do not conflict. See §4.4 for the fetch-time wait config.
strategy = "networkidle"          # or "domcontentloaded" / "load"
selector = ""                     # optional CSS selector for stubborn JS-rendered content
                                   # (e.g., "main article" or "[data-loaded]")
timeout_s = 10                    # hard cap on the post-loop wait — falls through on timeout instead of hanging

[render.lazy_load]
scroll_pause_ms = 800             # pause between scroll steps
max_scroll_steps = 50             # max iterations
max_scroll_seconds = 30           # wall-clock cap
layout_settle_ms = 250            # pause after scrollTo(0, 0) before the post-loop wait — see §6.5
```

### 6.8 Dependencies

- `web-fetch` (cross-skill via `skill_imports.use("web-fetch")`)
- `playwright` + Chromium (already required by `web-fetch`; reused)
- `beautifulsoup4` (used for `<base href>` injection, `strip_selectors` removal, and article-mode `selector` masking — preferred over string splicing because real-world `<head>` blocks are routinely malformed)
- `pyyaml` (manifest YAML / frontmatter serialization — see §8.5)
- python.org Python 3.12

### 6.9 File layout

```
~/.claude/skills/webpage-to-pdf/
  SKILL.md
  webpage-to-pdf.toml.example
  webpage_to_pdf/
    __init__.py            # exports `convert`
    config.py
    routing.py             # PDF passthrough vs HTML render branch
    pdf_render.py          # Playwright print-to-PDF + lazy-load + sticky flatten
    dom_ops.py             # BeautifulSoup helpers: <base href> injection, strip, article-mode masking
    manifest.py            # JSONL manifest writer (shared shape with webpage-to-md; see §8.10)
  tests/
    test_webpage_to_pdf.py
    fixtures/
      sample.html
      sample.pdf
```

**PDF passthrough — no frontmatter.** When the input URL resolves to `application/pdf`, `webpage-to-pdf` writes the bytes to `output_dir/<stem>.pdf` and appends a manifest row recording `passthrough=True`, `source_sha256`, fetch metadata, and converter identity. **No frontmatter** is written — PDFs don't carry YAML headers, and re-encoding the file just to embed metadata would corrupt downstream consumers. The manifest is the sole audit surface for PDF-passthrough inputs on the `webpage-to-pdf` side.

---

## 7. `apify-runner` — third-party API client

### 7.1 Public API

```python
from apify_runner import run, attach_to, iter_items, ApifyRunResult, ApifyError, ENV_AUTODISCOVER

result = run(
    actor="apify/cheerio-scraper",            # any Apify actor ID
    input_data={                               # actor-specific JSON
        "startUrls": [{"url": "https://example.com"}],
        "linkSelector": "a.article-link",
    },
    *,
    timeout_s=600,                             # max wait for completion
    poll_interval_s=5,
    abort_on_timeout=False,                    # see callout below — default False means timeout LEAVES the run billing
    max_cost_usd=None,                         # if set: poll usage.totalUsd; abort run if exceeded — see §7.7 (Apify reported usage lags actual cost; cap is best-effort, not a hard guarantee)
    cost_buffer_percent=0,                     # optional soft ceiling: trigger abort at max_cost_usd * (1 - buffer/100). Default 0 = no buffer
    dataset_mode="list",                       # "list" (default, in-memory) | "jsonl" (stream to file)
    output_path=None,                          # required when dataset_mode == "jsonl"
    env_file=ENV_AUTODISCOVER,                 # default: walk CWD upward to git-root for .env. Pass None to skip discovery (env-vars only). Pass an explicit Path to pin a file.
    cfg=None,
)
# Note: `resume_run_id` is NOT a parameter on run(). To reconnect to an existing run, use attach_to(run_id) — see below.

result.run_id           # e.g. "AbC1dEf2gHi3"
result.actor            # echoes the actor ID for audit trail
result.dataset_id       # e.g. "AbCdEf123" — retained on result so iter_items() can fetch it later
result.api_base         # e.g. "https://api.apify.com/v2" — retained for iter_items() against compatible deployments / API base override
result.status           # "SUCCEEDED" | "FAILED" | "TIMED-OUT" | "ABORTED"
result.items            # list[dict] (when dataset_mode == "list"); empty list when mode == "jsonl"
result.items_path       # Path to JSONL file (when dataset_mode == "jsonl"); None otherwise
result.item_count       # int — total items, regardless of mode
result.cost_usd         # float — pulled from run.usage.totalUsd; see §7.7 caveat about reporting lag
result.duration_s       # float — wall-clock from start to finish
result.started_at       # datetime
result.finished_at      # datetime
# Note: NO authentication token is stored on result. iter_items(result, refetch=True) re-resolves the token at call time via the same chain as run() (env_file -> .env walk -> os.environ).
```

> ⚠️ **Cost-risk callout — `abort_on_timeout=False` (the default):** when a `run()` call times out locally, the **Apify run continues running on Apify's infrastructure and continues accruing cost** until it completes naturally or hits the actor's own timeout. The local `ApifyTimeoutError` does NOT stop the remote run. Two options for handling:
> - **Set `abort_on_timeout=True`** to have the skill `POST /v2/actor-runs/{id}/abort` before raising. Money up to the abort point is still spent; this caps the bleed.
> - **Use the run ID** from the raised exception to call `attach_to(run_id)` later — the existing run's status, cost, and dataset can be retrieved without starting a fresh paid run.
>
> Callers who don't read this will be surprised to find their Apify dashboard showing a still-running, still-billing actor after their Python code raised. Default is `False` (don't abort) because aborting destroys partial work; the explicit gesture lives with the caller.

**Reconnecting to an in-flight run via `attach_to(run_id)`** (cost-saving feature for long jobs):

```python
# First call timed out locally; the run is still going on Apify
try:
    result = run(actor="apify/heavy-scraper", input_data={"urls": [...]}, timeout_s=300)
except ApifyTimeoutError as e:
    saved_run_id = e.run_id     # exception carries this — see §7.4

# Later — attach to the existing run; fetches the actor ID from the run record itself:
result = attach_to(
    saved_run_id,
    timeout_s=600,                       # wait up to another 10 min
    dataset_mode="list",                 # same dataset options as run()
    env_file=ENV_AUTODISCOVER,           # same auth resolution as run() — see §7.3
    cfg=None,
)
```

`attach_to(run_id)` skips the `POST /runs` step (no new paid run), polls the existing run, and retrieves the dataset on completion. Auth, dataset mode, JSONL atomic-write, and `max_cost_usd` work the same as `run()`. **`actor` is not passed** — it is read from the existing run record.

This is the only resume path. `run()` does not accept a `resume_run_id` argument; conflating "start a new run" and "attach to an existing run" in one function led to confusing semantics ("when is `actor` required vs ignored?"). `attach_to(run_id)` is the dedicated entry point.

**Streaming via `iter_items()`** (per-mode behavior, clarified):

```python
for item in iter_items(result):
    process(item)
```

| `result.dataset_mode` was | `iter_items()` behavior |
|---|---|
| `"list"` | Iterates `result.items` in memory (no API calls). |
| `"jsonl"` | Reads `result.items_path` line by line (no API calls). |

`iter_items()` does **not** re-query the Apify dataset API. The auth context is retained on `result` (`result.dataset_id`, `result.api_base`) for cases where a future call wants to re-fetch — but `iter_items()` itself works against what's already retrieved.

For a fresh fetch from API on demand, use `iter_items(result, refetch=True)` — re-queries the dataset endpoint with paginated reads. Useful if the run is still appending rows after the original `run()` returned.

**`result.items == []` is a valid non-error outcome** — Apify actor produced zero rows. Check `result.item_count` and `result.status == "SUCCEEDED"` to distinguish "empty result" from "run failed." `result.item_count == 0 and status == "SUCCEEDED"` means the scrape ran fine and found nothing.

### 7.2 Lifecycle

```
caller calls run(actor, input)
  ↓
POST /v2/acts/{actor}/runs           -> returns runId, datasetId
  ↓
GET /v2/actor-runs/{runId}           ← poll every poll_interval_s
  ↓                                    until status ∈ terminal_set
                                       OR elapsed > timeout_s
  ↓ (success)
GET /v2/datasets/{datasetId}/items   ← paginated (offset/limit; skill handles transparently)
  ↓
return ApifyRunResult
```

### 7.3 Auth — `.env` driven

**`env_file` parameter values** (sentinel-driven; default behaviors are explicit):

| Value | Behavior |
|---|---|
| `ENV_AUTODISCOVER` (default) | Walk CWD upward looking for `.env`, stopping at the first git-root or `$HOME`. Fall back to `os.environ` if no token found. |
| `Path("/explicit/path/.env")` | Use exactly this file. No walking. Falls back to `os.environ` if the file is absent or doesn't contain `APIFY_API_TOKEN`. |
| `None` | **Skip `.env` discovery entirely.** Read `APIFY_API_TOKEN` from `os.environ` only. |

**Why a sentinel.** Using `None` for both "default" and "skip" is overloaded: it can't simultaneously mean "do the standard walk" and "skip the walk." `ENV_AUTODISCOVER` is exported from the package alongside `run`, `attach_to`, etc., so callers can `from apify_runner import ENV_AUTODISCOVER` and pin the behavior they want.

**Resolution chain when `env_file = ENV_AUTODISCOVER`** (highest priority first):

1. `.env` files walking from CWD upward, **stopping at the first git-root** (a directory containing `.git/`) or `$HOME`, whichever comes first. The first `.env` found within those bounds wins.
2. `os.environ["APIFY_API_TOKEN"]` — fallback if no `.env` provides the token.
3. If none of the above, raise `ApifyAuthError`:
   ```
   ApifyAuthError: APIFY_API_TOKEN not found.
   Set it in <project>/.env (mode 600) or export it in your shell.
   Get a token from https://console.apify.com/account/integrations.
   ```

**Why .env walking stops at the git-root, not just `$HOME`:** without this, a project nested under `~/Dropbox/projects/<active-project>/` whose own `.env` lacks the token would silently inherit credentials from `~/Dropbox/projects/.env` (if one exists) or worse, an unrelated parent. Stopping at the git-root makes the token's source predictable per-project. `$HOME` is the secondary boundary for cases where the project isn't a git repo. **When the walk reaches `$HOME` without finding a git-root**, `apify-runner` emits an `INFO` log (`apify_runner: no git-root found in walk; APIFY_API_TOKEN resolved from <path or environment> (boundary was $HOME)`) so the absence of repo isolation is visible during debugging.

**Why `.env` takes precedence over `os.environ`:** projects on this machine document their credentials in `.env` files (per `reference_secret_management.md`); shell-exported variables tend to be cross-project leakage from one-off `export` commands. Defaulting to `.env` makes per-project credentials predictable. Callers who want to skip `.env` discovery and use only env-vars pass `env_file=None`; callers who want to pin a specific file pass an explicit `Path`.

**Security notes:**

- **Resolved path is logged at DEBUG level.** Log line: `apify_runner: resolved APIFY_API_TOKEN from <path>`. Callers running with `LOG_LEVEL=DEBUG` see exactly which file was used. Discovers cases where the wrong `.env` is being picked up — important now that the walk is bounded but still capable of crossing project subdirectories.
- **File mode check.** If the resolved `.env` has world-readable or group-readable bits set (any `0o077` bit), emit a `WARNING` log: `apify_runner: <path> has loose permissions (mode 0o<x>); should be 0o600`. The skill does not refuse by default — refusal would break workflows where the user has accepted the trade-off on a single-user laptop. Set `apify.strict_permissions = true` in config to upgrade the warning to an `ApifyAuthError`.
- **No token logging.** The token value is never logged. Path-resolution log lines and error messages reference the file path only.

### 7.4 Errors

All exceptions inherit from `ApifyError` for catch-all handling. Each one **carries enough metadata to inspect / clean up the run** even after the exception fires — critical for the `abort_on_timeout=False` case where the run is still going.

| Exception | Trigger | Attributes carried |
|---|---|---|
| `ApifyAuthError` | 401 from API, or token missing, or `strict_permissions = true` and `.env` mode loose | `env_file_path`, `mode_octal` (if a permissions failure) |
| `ApifyActorNotFoundError` | 404 on actor ID | `actor` |
| `ApifyRunFailedError` | run reached `FAILED` / `ABORTED` | `run_id`, `actor`, `status`, `cost_usd_at_failure`, `dataset_id`, `error_message` from the run |
| `ApifyTimeoutError` | exceeded caller-specified `timeout_s` | `run_id`, `actor`, `status_at_timeout`, `cost_usd_at_timeout`, `dataset_id`, `aborted` (bool — True if `abort_on_timeout=True` was honored). The `run_id` lets the caller use `attach_to(run_id)` later to reconnect. |
| `ApifyBudgetExceededError` | `max_cost_usd` exceeded mid-run; skill called abort before raising | `run_id`, `actor`, `cost_usd` (at abort), `max_cost_usd`, `dataset_id` |
| `ApifyDatasetError` | run succeeded but dataset retrieval failed, OR `max_dataset_items` / `max_dataset_bytes` exceeded | `run_id`, `actor`, `dataset_id`, `items_retrieved` (count before failure), `cause` (network / cap-exceeded / parse) |

**Pattern for failure recovery:**

```python
try:
    result = run(actor="apify/heavy", input_data={...}, timeout_s=300, abort_on_timeout=False)
except ApifyTimeoutError as e:
    log.warning(f"timed out at status={e.status_at_timeout}, cost so far ${e.cost_usd_at_timeout:.2f}")
    log.warning(f"run still going on Apify; attach later with run_id={e.run_id}")
    save_for_later(e.run_id)
except ApifyBudgetExceededError as e:
    log.warning(f"aborted at ${e.cost_usd:.2f} (cap ${e.max_cost_usd:.2f}); run_id={e.run_id}")
except ApifyRunFailedError as e:
    log.error(f"{e.actor} failed: {e.error_message}; spent ${e.cost_usd_at_failure:.2f}")
```

### 7.5 Pagination + memory profile + JSONL atomic-write

Apify dataset endpoint supports `offset` and `limit`. Skill auto-paginates with `limit=1000` per request.

**`dataset_mode = "list"` (default):** concatenates pages into `result.items` in memory. Sanity cap via config (`max_dataset_items`, default 10,000) raises `ApifyDatasetError` if exceeded. **Memory profile:** at 10,000 LinkedIn-style profile rows (~5-10 KB each), peak memory is 50-100 MB — fine for one-off runs but worth knowing for parallel calls.

**`dataset_mode = "jsonl"`:** streams pages directly to a JSONL file, one row per line. `result.items == []`; `result.items_path` is the written file. Has its **own** caps to prevent runaway disk usage:

```toml
[apify.dataset]
max_dataset_items = 10000          # used in list mode
jsonl_max_dataset_items = 100000   # higher cap for streaming mode
jsonl_max_dataset_bytes = 5_000_000_000   # 5 GB hard ceiling on the JSONL file
```

**JSONL cap behavior is run-state aware.** If either cap is exceeded:

- **While the run is still non-terminal** (status in `RUNNING` / `READY`): the skill calls `POST /v2/actor-runs/{id}/abort`, then raises `ApifyDatasetError(cause="cap_exceeded")` with `items_retrieved` set to the count written before abort. Aborting a still-running paid run caps the bleed.
- **After the run has already terminated successfully** (status `SUCCEEDED` / `FINISHED`): there is nothing to abort — the run is already billable and complete. The skill **stops retrieval** and raises `ApifyDatasetError(cause="cap_exceeded")` with the same `items_retrieved` count. Do not issue a no-op abort against a terminal run.

The distinction matters because `POST .../abort` against a terminal run returns an error from Apify; the skill must check status before acting.

**Atomic write semantics for JSONL:**

1. Open `output_path` with a `.tmp` suffix: `<output_path>.tmp`.
2. Stream dataset rows into the `.tmp` file as Apify yields them (one row per line).
3. On run-success path: `os.replace(<output_path>.tmp, <output_path>)` — atomic rename. Downstream consumers reading `output_path` see either the empty/non-existent state (before rename) or the complete file (after). Never a partial with a final-looking name.
4. On run-failure / timeout / budget-exceeded / cap-exceeded paths: behavior depends on `apify.dataset.on_partial`:
   - `on_partial = "rename"` (default): rename `<output_path>.tmp` to `<output_path>.partial.jsonl`. Lets the caller inspect what was retrieved before the failure.
   - `on_partial = "delete"`: delete `<output_path>.tmp`. Use when partial data is more dangerous than no data.

   **Never** leave a `.tmp` file at `<output_path>` itself, and never rename a partial to the final-looking `<output_path>` — downstream consumers must be able to trust `<output_path>` to be either complete or absent.

This protects bulk callers from reading a half-written JSONL file as if it were complete.

**`iter_items(result)`:** **does not re-fetch from API** by default — see §7.1. List mode iterates `result.items`; JSONL mode reads `result.items_path` line by line. Pass `refetch=True` to force a fresh paginated read against the dataset endpoint (useful only if the run is still appending rows after the original `run()` returned, which is rare).

Trade-offs:
| Mode | Best for | Memory | Disk | Replayable? |
|---|---|---|---|---|
| `"list"` | Small results, immediate use | High | None | Yes (data in `result.items`) |
| `"jsonl"` | Large results, batch processing | Low | One JSONL file (atomic write) | Yes (file persists) |
| `iter_items()` (default) | Process-on-demand without re-querying | Low | None | Yes (uses already-retrieved data) |
| `iter_items(refetch=True)` | Live re-read from API | Low | None | Network-dependent |

### 7.6 Configuration — `apify-runner.toml`

```toml
[apify]
poll_interval_s = 5
default_timeout_s = 600
default_dataset_mode = "list"               # "list" | "jsonl"
max_dataset_items = 10000                    # safety cap (list mode only)
abort_on_timeout = false                     # default; per-call override available
strict_permissions = false                   # if true, refuse loose-mode .env (§7.3)
api_base = "https://api.apify.com/v2"        # override for compatible deployments / API-base testing — rarely needed
cost_buffer_percent = 0                      # see §7.7 — abort when reported cost reaches max_cost_usd * (1 - buffer/100)

[apify.dataset]
on_partial = "rename"                        # "rename" -> <output_path>.partial.jsonl | "delete" -> remove
```

### 7.7 Cost surfacing + budget gate

`result.cost_usd` is the actor's `usage.totalUsd` from the run object. Real money. Callers can budget post-hoc:

```python
result = run(actor="some/expensive-actor", input_data={...})
if result.cost_usd > 1.50:
    log.warning(f"Expensive run: ${result.cost_usd:.2f}")
```

**`max_cost_usd` mid-run gate** *(reported usage can lag actual consumption by some amount; cap is best-effort, not a hard guarantee — final billed cost may exceed the cap by the lag amount)*: when set, the skill polls `usage.totalUsd` on each status check. The effective threshold is `max_cost_usd * (1 - cost_buffer_percent / 100)` — the optional `cost_buffer_percent` (config or per-call) lets callers compensate for the lag with a programmatic soft ceiling. If running cost exceeds the threshold, the skill immediately calls `POST /v2/actor-runs/{id}/abort` and raises `ApifyBudgetExceededError`:

```python
try:
    result = run(actor="some/expensive-actor", input_data={...}, max_cost_usd=2.00)
except ApifyBudgetExceededError as e:
    log.warning(f"Run aborted at ${e.cost_usd:.2f} (cap was ${e.max_cost_usd:.2f}). Run ID: {e.run_id}")
    # Money up to that point is still spent; this caps the bleed.
```

⚠️ **Treat this as a bleed limiter, not a hard budget guarantee.** Apify's reported `usage.totalUsd` lags actual consumption by some amount (compute that's run but not yet billed isn't reflected in the polling response). The final cost on the Apify dashboard **can exceed `max_cost_usd`** by the lag amount — typically modest (cents to single-digit dollars), but real. Plan a buffer when setting the cap if the budget is tight: if the hard ceiling is $5, set `max_cost_usd = 4.50`.

Caveat on pre-flight estimates: an actor's listed "$X per request" depends on input size, retries, and run duration — too unreliable to gate on at the start. Mid-run abort with a buffer is the practical compromise.

### 7.8 Dependencies

- **Stdlib only** — `urllib.request`, `urllib.parse`, `json`, `time`, `dataclasses`. Same as linkedin's `_apify.py` heritage. No `requests`, no extra packages.
- python.org Python 3.12

This zero-dep stance is deliberate. Any project can pull in `apify-runner` without committing to Playwright or other heavy infrastructure.

### 7.9 File layout

```
~/.claude/skills/apify-runner/
  SKILL.md
  apify-runner.toml.example
  apify_runner/
    __init__.py            # exports run, ApifyRunResult, ApifyError + subclasses
    config.py
    client.py              # HTTP + polling + pagination
    env.py                 # .env loader (extracted from linkedin _apify.py)
  tests/
    test_apify_runner.py
    fixtures/
      mock_run_response.json
      mock_dataset_items.json
```

### 7.10 Test strategy — always mocked

Tests never call the live Apify API. Fixtures cover all states (RUNNING, SUCCEEDED, FAILED, dataset pagination). No CI cost; no flakiness from upstream changes.

Live integration is the caller's responsibility. Each consumer project pre-flights with a known actor before running its real workflow.

---

## 8. Cross-cutting concerns

### 8.1 Cross-skill imports

The hand-rolled sys.path pattern is wrapped in a small helper so every consumer skill stops doing the path math itself:

```python
# ~/.claude/skills/<consumer>/<consumer-package>/skill_imports.py
"""Helper: import a sibling skill's package, with explicit invariant checks."""
import importlib
import sys
from pathlib import Path

# Layout invariant: this file MUST live at:
#   ~/.claude/skills/<consumer-skill>/<consumer-package>/skill_imports.py
# That makes parents[2] resolve to ~/.claude/skills/. Asserting this invariant
# converts a silently-wrong install (helper at unexpected depth, e.g. via a
# symlink farm or a developer copy) into a clear error rather than mis-imports.
_SKILLS_ROOT = Path(__file__).resolve().parents[2]
assert _SKILLS_ROOT.name == "skills", (
    f"skill_imports.py layout invariant violated: parents[2] resolved to "
    f"{_SKILLS_ROOT}, expected a directory named 'skills'. Helper must live at "
    f"~/.claude/skills/<skill>/<package>/skill_imports.py."
)


def use(skill_name: str) -> None:
    """Add ~/.claude/skills/<skill_name>/ to sys.path; assert the skill exists.

    Idempotent — safe to call multiple times. Raises ImportError on missing skill.
    """
    skill_dir = _SKILLS_ROOT / skill_name
    if not skill_dir.is_dir():
        raise ImportError(
            f"Required skill '{skill_name}' not found at {skill_dir}. "
            f"Install <skill_name>-skill.zip first or symlink to ~/.claude/skills/{skill_name}/."
        )
    skill_dir_str = str(skill_dir)
    if skill_dir_str not in sys.path:
        sys.path.insert(0, skill_dir_str)


def validate_imported(module_name: str, expected_skill: str) -> None:
    """After `use(<skill>)` and `import <module>`, call this to assert the module
    actually came from the expected skill directory — guards against package-name
    collisions (e.g., a globally-installed `pipeline` shadowing a sibling skill's
    `pipeline` package).
    """
    mod = importlib.import_module(module_name)
    if mod.__file__ is None:
        return                                            # namespace package; can't validate
    expected_prefix = str(_SKILLS_ROOT / expected_skill)
    if not str(Path(mod.__file__).resolve()).startswith(expected_prefix):
        raise ImportError(
            f"Expected '{module_name}' to come from {expected_prefix}, but it "
            f"resolved to {mod.__file__}. A globally-installed package may be "
            f"shadowing the sibling skill. Check sys.path order or rename one of them."
        )
```

**Skill package-name uniqueness convention:** every skill's Python package name (the directory inside the skill folder containing `__init__.py`) must be unique across `~/.claude/skills/`. Examples on this host: `webfetch`, `webpage_to_md`, `webpage_to_pdf`, `apify_runner`, `mdlint`, `swupdate`, `pipeline` (used by both `pdf-to-markdown` and `ocr` v1 — these are pre-existing collisions; new skills must not add to the list). When two skills share a package name, `validate_imported()` catches the collision at import time. Future-proof: rename collisions when both packages need to be active in the same process.

Caller pattern (in `webpage-to-md/webpage_to_md/__init__.py`):

```python
from .skill_imports import use
use('web-fetch')
use('pdf-to-markdown')
from webfetch import fetch
from pipeline import prepare_pdf       # pdf-to-markdown's package
```

Two benefits over the previous hand-rolled pattern:
- **Failure messages are uniform.** Any silent wrong-import (e.g., the skill is installed at a non-standard depth, or the `parents[2]` walk hits an unexpected directory because of a symlink) becomes a clear `ImportError` with the expected path.
- **Refactoring-friendly.** If the skills directory ever moves (unlikely, but possible), one helper changes instead of every consumer.

**`validate_imported()` is the canonical guard against package-name collisions.** Python's import system caches modules by name, so a globally-installed package — or a sibling skill imported earlier in the session — can shadow what `use(skill_name)` was meant to load. `validate_imported(module_name, expected_skill)` resolves the imported module's `__file__` and asserts it lives under `~/.claude/skills/<expected_skill>/`. Call it whenever a consumer imports a sibling skill's package by name, especially when the package name is one of the known collision risks (`pipeline`, etc.). The helper short-circuits cleanly on namespace packages (`__file__ is None`) so it doesn't break legitimate edge cases.

Same conceptual pattern OCR already uses for `sanitize-names`. Codified in `feedback_pipeline_ir_import_direction.md`. The helper formalizes it without introducing PYTHONPATH or symlink dependencies.

**Rules:**
- `web-fetch` and `apify-runner` are **leaf skills** within this family — they do not import any other skill.
- `webpage-to-pdf` imports only `web-fetch` from this family.
- `webpage-to-md` imports `web-fetch` from this family AND `pdf-to-markdown` from outside this family (the existing PDF processing skill, used for the PDF passthrough route).
- No skill in this family imports from `apify-runner`. The DIY trio and the third-party API client are independent paradigms.

### 8.2 Dependency footprint per skill

| Skill | Pip deps | Cross-skill deps | Heavy? |
|---|---|---|---|
| `web-fetch` | `requests`, `playwright` (+ `playwright install chromium`) | none | yes (Chromium ~300 MB) |
| `webpage-to-md` | `beautifulsoup4`, `markdownify`, `pyyaml` | `web-fetch`, `pdf-to-markdown` | inherits web-fetch |
| `webpage-to-pdf` | `beautifulsoup4`, `pyyaml` (Playwright reused via `web-fetch`) | `web-fetch` | inherits web-fetch |
| `apify-runner` | **stdlib only** | none | no |

**No `pymupdf` / `fitz` in `webpage-to-md`.** PDF metadata extraction is delegated to `pdf-to-markdown` via the `merge_provenance` kwarg (§5.9, Phase B.1') so the heavy PyMuPDF dep stays in one place.

`apify-runner`'s zero-dep stance is deliberate — projects that only need Apify shouldn't have to install Playwright or anything else.

### 8.3 Config loading convention

Each skill ships a `*.toml.example` template. Loader resolves config in this precedence (highest first):

1. **Explicit `toml_path` argument** to `load_config(toml_path)`.
2. **`CWD/<skill>.toml`** (per-project override).
3. **`~/.config/<skill>.toml`** (user-wide override).
4. **Baked defaults** in the skill's `config.py`.

```python
def load_config(toml_path: Path | None = None) -> dict:
    """Resolve config.

    Precedence: explicit toml_path > CWD/<skill>.toml > ~/.config/<skill>.toml > defaults.
    """
```

This precedence corrects the previous design's contradiction (one place said "CWD first," the docstring said "caller-supplied first"). Caller-supplied always wins.

Shape is consistent with `pdf2md.toml`, `ocr2.toml`, `markdown-lint.toml`. Existing skills should be updated to this precedence in a follow-up; this spec sets the convention going forward.

### 8.4 Error handling

Each skill defines its own base exception (`FetchError`, `ConvertError`, `ApifyError`) plus targeted subclasses. Callers catch the base class for "anything went wrong"; catch specifics when they want to retry/fall back. No bare `Exception` raises anywhere.

### 8.5 Frontmatter YAML serialization

YAML frontmatter is serialized via a YAML library (PyYAML's `yaml.safe_dump` with `allow_unicode=True, sort_keys=False, default_flow_style=False`), **never via hand-concatenated strings**. Hand-rolled string concatenation breaks on titles containing colons, quotes, newlines, `---` separators, leading/trailing whitespace, or non-ASCII characters — all of which are common in real-world page titles. PyYAML handles quoting, escaping, and multi-line block scalars correctly.

When loading frontmatter back (for re-conversions in §5.3 local input path), use `yaml.safe_load` with the same library. Round-trip fidelity is the contract.

### 8.6 Versioning discipline

Every skill's package exposes `__version__` (semver-ish: `MAJOR.MINOR.PATCH`):

```python
# webfetch/__init__.py
__version__ = "0.1.0"
```

**Increment policy:**
- **PATCH** (`0.1.0` -> `0.1.1`): bug fixes, internal refactors, no observable output change.
- **MINOR** (`0.1.0` -> `0.2.0`): new features, new config options with safe defaults, no breaking output changes.
- **MAJOR** (`0.1.0` -> `1.0.0`): breaking changes — output semantics change (frontmatter shape, manifest field renames, default behavior shifts).

The `converter_version` field in frontmatter and manifest rows reads from `__version__`. Consumers reading old archived outputs can compare `converter_version` against the current `__version__` to know whether re-running would produce a different result.

### 8.7 Deterministic clock for tests

Provenance fields use timestamps (`fetched_at`, `started_at`, `completed_at`, `re_converted_at`, `processed_at`). For snapshot tests to be stable, the timestamp source must be injectable.

Convention: each skill's package exposes a `_clock()` callable (default `datetime.now(timezone.utc)`). Tests inject a fake clock via monkey-patching:

```python
# In tests:
def test_frontmatter_provenance(monkeypatch):
    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("webfetch.http._clock", lambda: fixed)
    result = fetch("https://example.com")
    assert result.fetched_at == fixed
```

Without this, snapshot tests against frontmatter / manifest rows are inherently brittle — the timestamps drift on every run and require regex-stripping in assertions, which masks real changes.

### 8.8 Testing — three tiers

1. **Unit tests with no network** — every skill ships a `tests/` directory using pytest, fixtures for HTML/PDF samples, mocks for HTTP calls. Goal: full suite runs in <5 seconds, no external dependencies. Required.

2. **Integration tests with live URLs** — small, hand-curated set (a static blog post, a JS-rendered SPA, a PDF). Marked `@pytest.mark.integration`, NOT run in default suite. Run manually before shipping.

3. **Live cross-skill end-to-end** — for `webpage-to-md` and `webpage-to-pdf`, a small integration test that fetches a real URL, runs the full chain, asserts an expected output structure. Also gated on `@pytest.mark.integration`.

`apify-runner` tests are **always mocked** — no live Apify in CI. Live verification is the caller's responsibility.

### 8.9 SKILL.md template structure

```
# <skill-name> skill

<one-paragraph elevator pitch>

**Prerequisites:** <pip + cross-skill list>

## §1 — When to use this skill
## §2 — Public API
## §3 — Configuration
## §4 — Common traps
## §5 — Regression checks when updating this skill
```

Matches existing skills (`pdf-to-markdown/SKILL.md`, `ocr/SKILL.md`, `markdown-lint/SKILL.md`).

### 8.10 Output manifests (per converter run)

Each converter (`webpage-to-md`, `webpage-to-pdf`) appends one row to a `manifest.jsonl` in `output_dir` per conversion attempt — successes AND failures both record. Each row is **valid JSON** (no comments inside the row); explanatory notes live in the surrounding prose.

**Row shape (success — webpage-to-md):**

```json
{
  "manifest_schema_version": "1.0",
  "requested_url": "https://example.com/article",
  "final_url": "https://example.com/article",
  "started_at": "2026-05-03T10:29:55Z",
  "completed_at": "2026-05-03T10:30:00Z",
  "fetched_at": "2026-05-03T10:30:00Z",
  "content_type": "text/html",
  "content_type_source": "get_header",
  "fetch_method": "playwright",
  "http_status": 200,
  "source_artifact": "example-com__article__a1b2c3d4.html",
  "source_sha256": "7e8b3f9c0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",
  "derived_artifact": "example-com__article__a1b2c3d4.md",
  "converter": "webpage-to-md",
  "converter_version": "0.1.0",
  "status": "ok",
  "error_category": null,
  "error_message": null,
  "duration_ms": 4250,
  "selector": null,
  "extraction_strategy": "selector_then_body",
  "config_sha256": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4"
}
```

**Row shape (success — webpage-to-pdf, additional fields):** `webpage-to-pdf` rows include the fields above plus `render_mode`, `page_format`, `flatten_sticky`, `hide_fixed`, `live_double_fetch`, `render_html_sha256`, and (when persisted) `rendered_html_artifact`. `extraction_strategy` is omitted; `selector` is the article-mode CSS selector (§6.1) when set.

**Field-by-field rationale:**

- **`manifest_schema_version`** — `"1.0"` for the row shapes above. Bumped to `"1.1"` etc. when fields are added in a backward-compatible way; bumped to `"2.0"` if a field's meaning changes incompatibly. Lets readers reject rows they don't know how to parse.
- **`started_at` and `completed_at`** — DNS/auth failures may have no `fetched_at` because no body was retrieved. Row still records the attempt with `status = "failed"`.
- **`selector`, `render_mode`, `page_format`, `flatten_sticky`, `hide_fixed`, `extraction_strategy`** — output-determining parameters. Two conversions of the same URL with different selectors are not equivalent outputs; recording them lets a re-run reproduce the exact same artifact.
- **`config_sha256`** — SHA-256 hex digest of the effective merged config used for this conversion (after CWD/user/default precedence resolution). Pinpoints config drift across runs; two conversions with different `config_sha256` may diverge for non-obvious reasons.
- **`error_message`** — sanitized exception text on failure rows (truncated to 500 chars, no token values, no stack traces). Helps diagnose failures without reading separate logs.

**Failure-row example** (DNS failure on a URL):

```json
{
  "manifest_schema_version": "1.0",
  "requested_url": "https://nonexistent.example.com/article",
  "final_url": null,
  "started_at": "2026-05-03T10:32:00Z",
  "completed_at": "2026-05-03T10:32:30Z",
  "fetched_at": null,
  "content_type": null,
  "fetch_method": null,
  "http_status": null,
  "source_artifact": null,
  "source_sha256": null,
  "derived_artifact": null,
  "converter": "webpage-to-md",
  "converter_version": "0.1.0",
  "status": "failed",
  "error_category": "network",
  "error_message": "DNS resolution failed for nonexistent.example.com after 3 retries",
  "duration_ms": 30000,
  "selector": null,
  "extraction_strategy": "selector_then_body",
  "config_sha256": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4"
}
```

**Lock semantics — single-process append.** Manifest writing assumes a single-process consumer (per §11 out-of-scope: concurrency is the caller's responsibility). The skill does **not** acquire a file lock around the append. If a multi-process bulk caller is needed, the caller must coordinate manifest writes externally (e.g., write to per-process manifests then merge after; or use a process-pool with a single dedicated writer). Documented as a known limitation rather than papered over with a half-baked lock.

The manifest is the natural input for a future `web-archive` skill — out of scope for MVP, but the manifest format is designed to support it without rework.

### 8.11 Bundle convention

Each skill gets a transport bundle in `bundles/`:

```
bundles/
  web-fetch-skill/web-fetch/...        # mirror of ~/.claude/skills/web-fetch/
  web-fetch-skill.zip
  webpage-to-md-skill/...
  webpage-to-md-skill.zip
  webpage-to-pdf-skill/...
  webpage-to-pdf-skill.zip
  apify-runner-skill/...
  apify-runner-skill.zip
```

Built via `rsync -a --delete --exclude='__pycache__' ...` then `zip -qr`. Manual rebuild on ship is the established convention.

### 8.12 Cross-references in SKILL.md

`webpage-to-md`'s SKILL.md "Prerequisites" section explicitly says "depends on `web-fetch` skill being installed" with the install path. Future Claude Code sessions reading SKILL.md will know what's needed before invoking. Same for `webpage-to-pdf` -> `web-fetch`.

---

## 9. Implementation phasing

Four phases, each with explicit safety gates so working code is never broken.

### 9.1 Phase A — Build leaf skills (no consumer changes yet)

These have no upstream dependencies and can be built independently — could even be done in parallel.

| Order | Skill | Source | Est. |
|---|---|---|---|
| A.1 | **`web-fetch`** | New code; designs from §4. Lift any reusable bits from Profisee `scrape.py`'s `requests` setup; design Playwright path from scratch. | ~1 session |
| A.2 | **`apify-runner`** | Extract + generalize from linkedin's `_apify.py` (149 lines). The base structure exists in that file; new work covers error subclassing, mid-run cost gate, dataset_mode/JSONL output, abort_on_timeout, .env permissions warning, and the full mock test suite. | ~1 session |

**Each ships when:**
- Unit tests pass (mocked, no network)
- Manual integration smoke (`fetch("https://example.com")` returns 200 + HTML; an Apify run with a free actor succeeds)
- `bundles/<skill>-skill.zip` rebuilt

### 9.2 Phase B — Build mid-layer skills (still no consumer changes)

Depend on Phase A leaves. Build sequentially. Build `webpage-to-md` first — Markdown conversion is more structurally useful and lower-risk than PDF visual capture.

| Order | Skill | Source + scope | Est. |
|---|---|---|---|
| B.1 | **`webpage-to-md`** | New code wrapping `markdownify` for HTML->MD; PDF passthrough wrapping `pdf-to-markdown` with merged frontmatter (§5.9); `<base href>`/srcset URL normalization (§5.7); two-stage extraction with hooks for Readify (§5.6); filename collision policy (§5.8); local-input fast path with `<stem>.html.meta.json` sidecar (§5.3); content-determining frontmatter (selector, extraction_strategy, config_sha256). Profisee `_node_to_md()` is preserved as a side-by-side reference fixture (assertions are source-HTML driven per §5.5). | ~1 session |
| B.1' | **`pdf-to-markdown` contract change (cross-skill)** | Add `merge_provenance: dict | None = None` kwarg to `pdf_to_markdown.process()`. When set, prepend the dict to the produced MD's frontmatter (PDF-internal metadata wins on key collisions for `title`/`author`); return the merged dict on `PdfMdResult.frontmatter`. Required for B.1's PDF passthrough to produce coherent merged frontmatter without `webpage-to-md` importing PyMuPDF directly (§5.9). Ships in the same Phase B window as B.1; tracked separately because it modifies an existing skill. | ~0.25 session |
| B.2 | **`webpage-to-pdf`** | Playwright print-to-PDF with `"continuous"` (single-tall-page) default; CSS-injection via JS `getComputedStyle()` walk for sticky flattening (§6.6); incremental scroll loop for lazy-load (§6.5); `live` and `captured_html` render modes (§6.2) including `<base href>` injection in captured mode; live-mode `<stem>.rendered.html` persistence (§6.2); article-mode `selector` (§6.1); `strip_selectors` config for cookie-banner / chat-widget removal (§6.6); precedence rule for sticky options (§6.6). | ~1 session |

**Each ships when:** Unit + integration tests green per the per-skill acceptance gates in §9.5, both URL-input and local-input paths exercised, bundle rebuilt. (Phase B.1's gate explicitly includes the new `merge_provenance` round-trip via B.1'.)

### 9.3 Phase C — Migrate consumers (one at a time, carefully)

Different risk profiles per project; migration order matches risk mitigation.

#### 9.3.1 AAA-radio first (highest production risk, but best feedback loop)

AAA-radio runs **weekly via launchd**. A migration bug would show up as a failed weekly run — visible quickly, but disruptive when it happens.

**Strategy: parallel run with diff verification.**

1. Add `fetch_chart_v2.py` next to existing `fetch_chart.py`. New module uses `web-fetch`. Old module untouched.
2. The weekly orchestrator (`weekly_run.py`) calls **both** for one cycle: old produces the canonical output, new produces a candidate output, diff them. Flag any mismatch in the run log.
3. If three consecutive weekly cycles diff-clean, switch the default to `fetch_chart_v2.py`. Keep `fetch_chart.py` for one more cycle as fallback.
4. After fourth clean cycle, delete `fetch_chart.py` and rename `_v2` to canonical. Drop `selenium>=4.15` from `requires.txt`.

**Diff is on parsed structured output, not raw HTML.** AAA-radio's network layer produces HTML; its `parse_top60`/`parse_surging_emerging`/`parse_recurrent`/`parse_chart_dates` functions produce structured Python dicts and CSV rows. The diff compares those structured outputs (track listings, ranks, chart dates) — not the raw fetched HTML. Whitespace/timestamp/script-tag drift in the source HTML doesn't reach the diff. This is the right comparison granularity: it catches real semantic divergence and ignores cosmetic noise.

**Future hook for AAA-radio:** once `web-fetch.toml` `[fetch.conditional_get]` is implemented (deferred per §4.4), the weekly run can pass `if_modified_since` from the previous week's `Last-Modified` header. CDX charts that haven't changed produce a 304 response; AAA-radio can short-circuit to "no new chart this week" without re-fetching the body. Concrete first consumer for the conditional GET feature.

**Total elapsed time:** ~4 weeks (gated on weekly runs). Hands-on work: ~2 sessions (initial parallel build, final cleanup).

#### 9.3.2 linkedin second (lowest complexity)

linkedin is deferred per the registry — no active use, but `_apify.py` is the heritage source for `apify-runner`. Migration is mostly mechanical.

**Strategy: in-place replacement with smoke test.**

1. Replace `_apify.py` body with a thin shim:
   ```python
   import sys
   sys.path.insert(0, str(Path.home() / '.claude/skills/apify-runner'))
   from apify_runner import run as _run
   # legacy wrapper that adapts to existing call shape
   ```
2. Run the existing `scripts/scrape_profiles.py` against a single sample profile URL — confirm it still produces the expected output shape.
3. If green, simplify `scrape_profiles.py` to call `apify_runner.run()` directly; drop the shim.
4. Update `linkedin/CLAUDE.md` to reference the skill.

**Total elapsed time:** ~30 min hands-on.

#### 9.3.3 Profisee third (most code, deferred status)

Profisee has three DIY scrapers. Project is "deferred — intelligence gathering complete." Low immediate risk because nothing actively runs; migration is code archaeology + extraction validation.

**Strategy: per-scraper migration with sample-data validation.**

| Profisee module | Migrates to |
|---|---|
| `scrape.py` (resources index crawler) | `web-fetch` + project-specific parser kept locally |
| `scrape_blog.py` (HTML->MD blog scraper) | `webpage-to-md` (canonical engine source) + lightweight project glue |
| `scrape_inventory.py` (URL->PDF bulk download) | `webpage-to-pdf` + project-specific manifest tracker |
| `submit_forms.py` (Marketo form automation) | **NOT MIGRATED** — `web-form-submit` skill not in scope. Stays in Profisee until that skill ships. |

**Per scraper:**
1. Branch the project file (e.g., `scrape_v2.py`).
2. New file uses skills; old file stays as reference.
3. Run new file against a small sample (a known existing blog post / known PDF URL) and diff against the existing archived output in `Profisee/scraped/`. Normalize whitespace before comparing.
4. If clean, archive old file and rename new file to canonical.

**Total elapsed time:** ~1.5 sessions hands-on.

### 9.4 Phase D — Cleanup + memory + REGISTRY

After all migrations:

1. Update `projects/REGISTRY.md` for each migrated project: drop `selenium` / `requests`-wrt-scraping references; add an `Expected missing imports` annotation for each consumer pointing at which sibling skill it sys.path-imports (so `check-registry.py`'s scan stays green).
2. Update each project's `CLAUDE.md` to point at the skill catalog.
3. Add a `feedback_*.md` memory codifying the four-skill stack and the cross-skill import pattern (mirrors `feedback_pipeline_ir_import_direction.md` shape).
4. Remove the four G3 factoring candidates from `project_registry_bootstrapped.md`'s open list — they're now extracted.

### 9.5 Per-skill acceptance gates

Each skill must satisfy these specific test scenarios before it ships. "Tests pass" alone is too vague; these are the hard gates.

**`web-fetch`:**
- Static-HTML page (e.g., known blog post) — fetched via HTTP, returns 200, content-type detected from header.
- Server-rendered HTML at a non-`.pdf` URL but with `application/pdf` Content-Type — magic-byte stream check correctly identifies (or rejects) without committing to full download.
- PDF URL ending in `.pdf` — content_type_source = "url_suffix", body returned as bytes.
- JS-rendered SPA (mocked `__NEXT_DATA__` fixture) — falls back to Playwright via render-fallback heuristic.
- 404 fixture — raises `FetchError(error_category="not_found")`.
- 429 fixture with `Retry-After: 5` — honors header, retries once after 5 s.
- Cloudflare challenge fixture — raises `FetchError(error_category="bot_challenge")`, does NOT fall back to Playwright (proves §1.5 boundary).
- Per-domain override fixture — `[[fetch.domain_overrides]]` with `fetch_method = "playwright"` skips heuristic.
- Redirect-loop fixture (Playwright) — raises `FetchError(error_category="redirect_loop")` instead of timing out.

**`webpage-to-md`:**
- HTML URL -> MD output with absolute links (relative URLs normalized via `<base href>` priority then `final_url`).
- HTML URL with `srcset` images — both `src` and `srcset` URLs rewritten.
- HTML URL -> source `<stem>.html` saved alongside `<stem>.md`.
- PDF URL -> source `<stem>.pdf` saved + merged frontmatter includes both web-fetch metadata and PDF internal metadata.
- Local file input (`Path` or `file://`) -> no network call; MD produced; frontmatter records `re_converted_at`.
- Manifest row appended for both success and failure cases.
- `selector` parameter narrows extraction to specific subtree.
- Profisee regression fixture — `markdownify` output passes the seven concrete assertions in §5.5 (heading parity, link parity, list parity, table parity-on-non-colspan, no CTA boilerplate, title preserved, non-empty).
- `extraction.strategy = "selector_then_readability_then_body"` raises `ConvertConfigError`, not `NotImplementedError`.

**`webpage-to-pdf`:**
- HTML URL with `render_mode="live"` -> PDF rendered via Playwright navigating to original URL; `live_double_fetch=True` recorded.
- HTML URL with `render_mode="captured_html"` -> PDF rendered from saved HTML with `<base href>` injection.
- PDF URL -> passthrough; bytes copied to `<stem>.pdf` without re-render.
- Tall page (longer than 200 inches) -> auto-fall-back from `"continuous"` to `"screen-paginated"` with one-line warning log.
- Sticky element fixture (class-based CSS) -> `flatten_sticky=True` + `getComputedStyle()` walk converts to `static`.
- `strip_selectors = [".cookie-banner"]` -> element removed pre-render; not in PDF.
- Lazy-load fixture — incremental scroll loop fires until `scrollHeight` stabilizes; image references load.

**`apify-runner`:**
- Mocked successful run -> `result.items` populated, `cost_usd` set, manifest fields complete.
- Mocked failed run -> `ApifyRunFailedError` raised with `run_id`, `actor`, `cost_usd_at_failure` attributes.
- Mocked timeout with `abort_on_timeout=True` -> calls abort endpoint before raising; `aborted=True` on exception.
- Mocked timeout with `abort_on_timeout=False` (default) -> exception carries `run_id` for `attach_to()` recovery.
- Mocked `max_cost_usd` exceeded mid-run -> `ApifyBudgetExceededError` raised; abort called.
- `dataset_mode="jsonl"` -> atomic write to `.tmp` then `os.replace`; partial preserved on failure.
- `dataset_mode="jsonl"` cap exceeded mid-stream -> run aborted, `ApifyDatasetError(cause="cap_exceeded")` raised.
- Pagination fixture (multiple `limit=1000` pages) -> all items concatenated correctly.
- `iter_items(result)` reads from in-memory list (list mode) or file (jsonl mode); does not re-query API by default.
- `iter_items(result, refetch=True)` re-queries the API with paginated reads.
- `attach_to(run_id)` -> skips POST /runs, polls existing run, retrieves dataset on completion (the only resume path; `run()` does not accept `resume_run_id`).
- `.env` walking stops at git-root (mocked git project structure).
- `.env` permissions warning at `0o644`; refusal at `strict_permissions=True`.
- Zero-items run is `status="SUCCEEDED"`, `item_count=0` — distinguishable from failure.

These are the hard gates. New scenarios surfaced during integration with real consumers (Profisee, AAA-radio, linkedin) become regression fixtures, added to the relevant skill's test suite.

### 9.6 Total effort summary

| Phase | Scope | Sessions |
|---|---|---|
| A — Leaf skills | 2 skills (`web-fetch`, `apify-runner`) | ~2 |
| B — Mid-layer skills + cross-skill contract | `webpage-to-md`, `pdf-to-markdown` `merge_provenance`, `webpage-to-pdf` | ~2.25 |
| C — Migrations | AAA-radio + linkedin + Profisee | ~3.5 hands-on (+ AAA-radio's 4-week parallel verification window) |
| D — Cleanup | docs + memory + registry | ~0.5 |
| **Total** | | **~8–12 sessions hands-on, ~5–7 calendar weeks** (range reflects: PyYAML serialization, manifest schema versioning, deterministic clock, JSONL atomic write, `attach_to`, budget cost-buffer, live/captured PDF modes, sidecar provenance, per-skill acceptance gates — all of which expand the implementation surface beyond the original ~8-session estimate). |

---

## 10. Risk mitigations

- **No consumer touches until Phase C.** Skills must be working in isolation first. Any bug is contained to the skill being authored, not breaking three projects at once.
- **Parallel-run + diff verification for production code (AAA-radio).** Never replace working scraping with untested code. The 4-week window is gated on real weekly runs producing identical outputs.
- **Sample-output diffs for deferred projects (Profisee/linkedin).** Even without active use, archived outputs serve as regression baseline.
- **`apify-runner` tests use mocks.** Live integration costs Apify credits; CI runs free.
- **`web-fetch` render-fallback heuristic is configurable and layered.** Primary signal is text-content (`< 200 chars` after stripping); secondary is byte count (`< 2 KB`); tertiary is framework markers checked on raw HTML (`__NEXT_DATA__`, `__INITIAL_STATE__`, etc.). A `[[fetch.domain_overrides]]` table provides explicit per-host pinning when the heuristic misfires. Challenge-page detection runs **before** render-fallback so blocked pages error immediately rather than triggering a Playwright fallback that wouldn't bypass anyway.
- **`webpage-to-pdf` 200-inch sanity cap.** Falls back to paginated mode with a warning if a page is too tall to fit in a single PDF page.

---

## 11. Out of scope

Deliberately excluded from this design to keep it shippable:

- **`web-form-submit` skill.** Profisee's `submit_forms.py` (Marketo automation) stays in-project until a second consumer needs it. **Note for future scoping:** "form submission" is not one engineering problem but three — (1) standard HTML forms (POST to action URL with form-encoded body, no JavaScript), (2) Marketo/HubSpot/Pardot form APIs (hidden field injection, tracking munchkin/pixel cookies, vendor-specific endpoints), (3) JavaScript-driven forms (React/Vue components that intercept submit events, build payloads via JS, post to GraphQL/JSON APIs). These have meaningfully different architectures. A future `web-form-submit` skill spec must explicitly scope which of the three (or which combination) it handles before implementation begins.
- **`web-crawl` skill.** Index pagination + URL discovery. Useful for first-time scrapes of a domain; not needed when caller already has a curated URL list. Defer until it has a clear consumer.
- **Archive folder / `web-archive` skill.** "Move accepted MD outputs to a long-term archive" is the caller's job for now. A future `web-archive` skill could handle deduplication via content hash, organized by domain/date — the §8.10 manifest format is designed to be its natural input. Premature now; sketch on backlog when a consumer needs it.
- **Browser extensions in `web-fetch`.** The config field `extensions = []` exists as a future hook; implementation deferred. When implemented, will switch to `chromium.launch_persistent_context()` with `headless=False`.
- **Browser session reuse for bulk fetches.** Each `fetch()` call currently launches its own Chromium process when Playwright is needed. Cold-start is 3-5 s on this 2017 Intel host; for bulk consumers (Profisee `scrape_inventory.py` post-migration) that overhead adds up. A `session()` context manager that amortizes the launch across many fetches is a planned optimization. Defer to first real bulk consumer feeling the pain.
- **Authenticated scraping with `storage_state`.** Playwright supports cookie/localStorage persistence for logged-in sessions, which is exactly the surface where credential leaks, token theft, and personal-data scraping concerns intersect. **Explicitly deferred with a security model required before implementation.** Adding it to `web-fetch` requires answering: where do session credentials live (.env? Keychain?), what's the cleanup contract (cleared after run? persisted?), what does `fetched_at` mean for content visible only to that user, and how does the §1.5 boundaries section change? None of those answers exist yet; deferring until they're worked out separately.
- **Concurrency / batch APIs.** `web-fetch.fetch()` is synchronous, single-URL. Bulk callers manage concurrency themselves (threads or asyncio). Skill stays simple.
- **TLS/JA3 fingerprint customization.** Modern enterprise blocking stacks fingerprint TLS handshakes; a fully evasive client would need `curl-impersonate` or similar low-level tooling. The DIY trio explicitly does not pursue this — the family's separation between `web-fetch` (open-web, JS-render) and `apify-runner` (third-party, when otherwise-appropriate) covers the intent properly. Sites that block at the TLS layer **may** be addressed via `apify-runner` if the legal/contractual context permits; the boundary in §1.5 still applies — paying a third party does not grant rights the consumer doesn't already have.

---

## 12. Open questions resolved during design

For audit: questions that came up in brainstorming and how they were resolved.

| Question | Resolution |
|---|---|
| One umbrella skill, 5 focused skills, or 2 by paradigm? | **5 focused skills** (then trimmed to 4: `web-crawl` and `web-form-submit` deferred). |
| Auto-detect HTTP/Playwright fallback, or caller-driven? | **Auto-detect with manual override** via config. |
| Naming: `web-html-to-md` or `webpage-to-md`? | **`webpage-to-md`** — input is a URL/page, not a string of HTML. |
| `webpage-to-md` PDF persistence: temp / explicit / always? | **Always alongside MD.** Source artifact preservation by default. |
| Apify in or out? | **In.** linkedin already uses it; LinkedIn-class blocking sites need it. |
| Default page format for PDF: Letter / A4 / something else? | **`"continuous"`** — single tall page, computer-screen aspect (alias `"screen"` accepted). Avoids pagination artifacts. |
| Browser extensions in `web-fetch`? | **Future hook only.** Plan for it; don't build it. |
| AAA-radio migration window? | **4 weeks parallel-run + diff verification.** Production code, weekly cadence. Diff is on parsed structured output, not raw HTML. |
| HTML->MD engine: Profisee extraction or markdownify? | **Commit to `markdownify`** (added 2026-05-04 after reviewer feedback). Profisee's `_node_to_md` becomes a regression fixture proving equivalence on known-good corpora. |
| `webpage-to-pdf` `file://` reload reproducibility? | **Two render modes added.** `"live"` (default, navigates to original URL — high fidelity, lower reproducibility) vs `"captured_html"` (loads saved HTML with injected `<base href>` — strict reproducibility, lower fidelity). Caller chooses; default `"live"`. |
| Page format naming: `screen` vs something less ambiguous? | **`"continuous"` is canonical** (alias `"screen"` accepted for backward compatibility). Disambiguates from `media="screen"` which is a separate stylesheet emulation concept. |
| Scraping ethics / compliance language? | **§1.5 added** with explicit boundaries: no auth/CAPTCHA bypass, robots.txt is consumer's responsibility, conservative rate limits, provenance preserved per fetch, Apify doesn't grant unobtained rights. |
| Apify large datasets — list or stream? | **Both supported.** `dataset_mode = "list"` (default, in-memory, capped at 10k) and `"jsonl"` (stream to file, uncapped). Plus `iter_items()` lazy iterator for process-on-demand. |
| `apify-runner` budget gate? | **Mid-run abort via `max_cost_usd` parameter.** Polls `usage.totalUsd`; aborts when exceeded. Pre-flight estimates too unreliable to gate on. |

---

## 13. Next steps when implementation begins

The session that picks this up should:

1. Read this spec end-to-end.
2. Produce an implementation plan from this spec — using the local planning skill if available, otherwise drafting one inline. The plan should be **per-phase**, not monolithic: Phase A (leaf skills) gets one plan, Phase B (mid-layer) gets another, Phase C migrations are per-project plans.
3. Start with Phase A.1 (`web-fetch`) — the foundational primitive. Phase A.2 (`apify-runner`) can run in parallel since the two have no shared code.
4. Defer all migration work until Phases A and B are complete and the bundle has shipped at least one round of integration smoke tests.

Each phase is approved as its own work increment; this spec is the design baseline, not a single-pass implementation plan.
