# scraping

A Claude Code plugin bundling four web-scraping skills:

- **web-fetch** — URL → bytes with HTTP→Playwright auto-fallback, content-type sniffing, redirect chain, and provenance hashing.
- **webpage-to-md** — URL → Markdown. Routes PDF passthrough vs HTML conversion. (Phase B.)
- **webpage-to-pdf** — URL → PDF. Default `"continuous"` (single-tall-page) format for visual fidelity. (Phase B.)
- **apify-runner** — Stdlib-only Apify v2 actor client. Used when open-web access is blocked. (Phase A.)

## Installation

```bash
claude marketplace add github:jacefrey/scraping
claude plugin add scraping@scraping
```

After installation, skills are available as `scraping:web-fetch`, `scraping:webpage-to-md`, etc.

## Boundaries

These skills do **not** implement stealth browser fingerprinting, CAPTCHA solving, credential replay, TLS/JA3 impersonation, or anti-bot evasion. See `docs/spec.md` §1.5 for the full non-goals.

## Status

- **Phase A** — `web-fetch` foundation (types, config, detection helpers): in progress. `apify-runner`: not started.
- **Phase B** — `webpage-to-md`, `webpage-to-pdf`: not started.
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
