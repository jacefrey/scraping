# apify-runner skill

Stdlib-only Apify v2 API client. Submit an actor + input, poll until done,
retrieve the dataset, return a typed result. Used by `linkedin` (and any
future consumer that needs to scrape behind enterprise blocking).

**Prerequisites:**
- python.org Python 3.12 at `/Library/Frameworks/Python.framework/Versions/3.12/`
- An Apify API token from https://console.apify.com/account/integrations
- A `.env` file (mode 600) holding `APIFY_API_TOKEN=...` OR the same env-var exported in the shell

No pip dependencies. The skill uses only stdlib (`urllib.request`,
`urllib.parse`, `json`, `time`, `dataclasses`, `pathlib`, `logging`).

## §1 — When to use this skill

Use `apify-runner` when a target site is blocked by enterprise anti-bot
infrastructure that the open-web `web-fetch` skill cannot reach (LinkedIn,
Twitter/X, Instagram, sites with TLS/JA3 fingerprinting). Apify costs real
money — see §4 below.

For sites where ordinary HTTP/JS rendering works, prefer `web-fetch`
(or `webpage-to-md` / `webpage-to-pdf` in Phase B) — those are free.

## §2 — Public API

```python
from apify_runner import (
    run, attach_to, iter_items,
    ApifyRunResult, ApifyError, ApifyBudgetExceededError, ApifyTimeoutError,
    ENV_AUTODISCOVER,
)

# Submit + poll + retrieve dataset.
result = run(
    actor="apify/cheerio-scraper",
    input_data={"startUrls": [{"url": "https://example.com"}]},
    timeout_s=600,                # max wait for completion
    poll_interval_s=5,
    abort_on_timeout=False,       # see Common traps
    max_cost_usd=2.00,            # best-effort cap; reported usage lags
    cost_buffer_percent=10,       # effective cap = $1.80
    dataset_mode="list",          # "list" (in-memory) | "jsonl" (file)
    output_path=None,             # required when dataset_mode="jsonl"
    env_file=ENV_AUTODISCOVER,    # default; walk to git-root for .env
    cfg=None,                     # optional pre-loaded config
)

# Reconnect to an in-flight run later (no new POST, no extra cost):
result = attach_to(saved_run_id, timeout_s=600)

# Iterate items (no API call by default):
for item in iter_items(result):
    process(item)

# Force a fresh API read (rare; only when run is still appending):
for item in iter_items(result, refetch=True):
    process(item)
```

### `ApifyRunResult` fields

See `docs/superpowers/specs/2026-05-03-scraping-design.md` §7.1 (inside the
plugin repo). Key fields: `run_id`, `actor`, `dataset_id`, `api_base`,
`status`, `items` (list mode) / `items_path` (jsonl mode), `item_count`,
`cost_usd`, `duration_s`, `started_at`, `finished_at`.

### Error hierarchy

All raise `ApifyError` (the common base). Subclasses carry rich metadata
for cleanup/inspection — critical when `abort_on_timeout=False` leaves a
paid run going on Apify:

- `ApifyAuthError` — missing token or 401 from API
- `ApifyActorNotFoundError` — 404 on the actor ID
- `ApifyRunFailedError` — run reached `FAILED` / `ABORTED` (carries `cost_usd_at_failure`)
- `ApifyTimeoutError` — exceeded local `timeout_s` (carries `run_id` for `attach_to()` recovery; `aborted` flag)
- `ApifyBudgetExceededError` — `max_cost_usd` exceeded; abort attempted (carries `cost_usd`, `max_cost_usd`)
- `ApifyDatasetError` — JSONL cap exceeded or pagination failed (carries `items_retrieved`, `cause`)

## §3 — Configuration

Copy `apify-runner.toml.example` to your project's CWD or
`~/.config/apify-runner.toml`. Precedence: explicit `toml_path` arg to
`load_config()` > `CWD/apify-runner.toml` > `~/.config/apify-runner.toml`
> baked defaults.

Or pass an in-memory `cfg` dict directly to `run()` / `attach_to()`.

### Auth — `.env` resolution

`env_file` parameter values:

- `ENV_AUTODISCOVER` (default) — walk CWD upward to first `.git/` dir or
  `$HOME`; uses the first `.env` found within bounds. Falls back to
  `os.environ["APIFY_API_TOKEN"]` if no `.env` yields a token.
- `Path("/explicit/path/.env")` — use this file directly.
- `None` — skip `.env` discovery entirely; read `APIFY_API_TOKEN` from
  `os.environ` only.

`.env` file permissions are checked: a warning fires if mode allows
group/world read (`0o077` bits set). Setting `[apify].strict_permissions = true`
in config upgrades the warning to a refusal.

## §4 — Common traps

- **`abort_on_timeout=False` (the default) leaves a paid run going on
  Apify.** When `run()` raises `ApifyTimeoutError`, the actor is still
  executing on Apify's infrastructure and continues to accrue cost. Use
  the `run_id` from the exception to call `attach_to(run_id)` later, or
  set `abort_on_timeout=True` to stop the bleed (destroys partial work).
- **`max_cost_usd` is best-effort, not a hard guarantee.** Apify's reported
  `usage.totalUsd` lags actual consumption; final cost on the dashboard
  can exceed the cap by the lag. Set `cost_buffer_percent=10` (or similar)
  to leave a safety margin.
- **JSONL atomic write.** `dataset_mode="jsonl"` writes to `<output_path>.tmp`,
  then `os.replace` on success — `<output_path>` is never partial. On
  failure (cap exceeded, run failed), the `.tmp` is renamed to
  `<output_path>.partial.jsonl` (or deleted, per `[apify.dataset].on_partial`).
- **`.env` discovery is bounded.** The walk stops at the first `.git/` dir
  or `$HOME`. A `.env` above the git-root is NOT picked up — protects
  against accidentally inheriting credentials from an unrelated parent
  directory.
- **Tests are always mocked.** `test_run_*.py` patches `_post_json`,
  `_get_json`, `_paginated_dataset_items`, and `time.sleep`. Live
  integration is the consumer's responsibility — pre-flight with a known
  free actor (e.g., `apify/test-actor`) before running real workflows.

## §5 — Regression checks when updating this skill

```bash
cd ~/.claude/skills/apify-runner
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v
```

All tests use mocks; the suite runs in <1 second and never touches the
network. There are no integration tests by design — Apify costs real
money per call, so live integration is the consumer's responsibility,
not part of CI.
