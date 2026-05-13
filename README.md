# scraping

A Claude Code plugin bundling four web-scraping skills:

- **web-fetch** — URL → bytes with HTTP→Playwright auto-fallback, content-type sniffing, redirect chain, and provenance hashing.
- **webpage-to-md** — URL → Markdown with persisted source HTML, frontmatter, and a JSONL manifest. Local-input fast path with sidecar provenance.
- **webpage-to-pdf** — URL → PDF via Playwright print-to-PDF. `live` mode (default, navigates to original URL) or `captured_html` mode (renders saved HTML with injected `<base href>`). PDF inputs pass through unchanged.
- **apify-runner** — Stdlib-only Apify v2 actor client. Used when open-web access is blocked.

## Installation

```bash
claude plugin marketplace add jacefrey/scraping
claude plugin install scraping@scraping
```

After installation, skills are available as `scraping:web-fetch`, `scraping:webpage-to-md`, etc.

## Boundaries

These skills do **not** implement stealth browser fingerprinting, CAPTCHA solving, credential replay, TLS/JA3 impersonation, or anti-bot evasion. See [docs/superpowers/specs/2026-05-03-scraping-design.md](docs/superpowers/specs/2026-05-03-scraping-design.md) §1.5 for the full non-goals.

## Status

- **Phase A** — `web-fetch` and `apify-runner`: complete (v0.2.0).
- **Phase B** — `webpage-to-md` and `webpage-to-pdf`: complete (v0.3.0).
- **Phase C** — Consumer migrations (AAA-radio, linkedin, Profisee): not started.

## Development

This is a Claude Code plugin. Skills are authored in `skills/<name>/` and symlinked into `~/.claude/skills/` for local development:

```bash
ln -sf "$(pwd)/skills/web-fetch" ~/.claude/skills/web-fetch
```

Test a skill:

```bash
cd skills/web-fetch
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v -m "not integration"
```

## Host

Built for macOS 13 Intel (2017 MacBook Pro). Python 3.12 at `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`.

## License

MIT — see [LICENSE](LICENSE).
