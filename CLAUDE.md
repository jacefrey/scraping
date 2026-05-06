# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

`scraping` is a Claude Code **plugin** that bundles a coherent four-skill family for retrieving web content with provenance:

1. **web-fetch** — `URL → bytes` with HTTP→Playwright auto-fallback. The single network primitive.
2. **webpage-to-md** — `URL → Markdown`. Routes PDF passthrough vs HTML conversion. (Phase B; not yet built.)
3. **webpage-to-pdf** — `URL → PDF` with `"continuous"` page format default for fidelity. (Phase B; not yet built.)
4. **apify-runner** — stdlib-only Apify v2 actor client for sites that block ordinary public access. (Phase A; not yet built.)

Plus a fifth product family role: **none of these skills do "stealth" scraping.** They circumvent no technical access controls. See `docs/superpowers/specs/2026-05-03-scraping-design.md` §1.5 (Scraping boundaries) for the explicit non-goals.

## Architecture

### Plugin shape

```
scraping/
├── .claude-plugin/
│   ├── plugin.json          # plugin manifest
│   └── marketplace.json     # marketplace entry (single-plugin marketplace)
├── .claude/
│   └── settings.json        # default model for working in this repo
├── skills/
│   ├── web-fetch/           # SKILL.md + Python package + tests + fixtures
│   ├── webpage-to-md/       # (future)
│   ├── webpage-to-pdf/      # (future)
│   └── apify-runner/        # (future)
├── docs/
│   ├── spec.md              # design spec (canonical)
│   └── phase-a-plan.md      # Phase A implementation plan
└── CLAUDE.md
```

### Skill location

Skills live at `skills/<name>/` in this repo. The repo is the source of truth. For local development, symlink each skill into `~/.claude/skills/`:

```bash
ln -sf "$(pwd)/skills/<name>" ~/.claude/skills/<name>
```

Verify: `ls -la ~/.claude/skills/<name>/`

For consumers who install the plugin via the marketplace, Claude Code caches the plugin at `~/.claude/plugins/cache/scraping/scraping/<version>/skills/<name>/` and exposes the skills as `scraping:<name>`.

### Cross-skill imports

Skills inside this plugin import each other via `skill_imports.py` (see `docs/superpowers/specs/2026-05-03-scraping-design.md` §8.1 for the canonical pattern). The helper resolves siblings by walking `parents[2]` from the calling module — that lands on `skills/` regardless of whether the plugin is invoked from a symlink (development) or the marketplace cache (production).

```python
from .skill_imports import use, validate_imported
use("web-fetch")
from webfetch import fetch
validate_imported("webfetch", expected_skill="web-fetch")
```

### Test layout

Each skill carries its own `tests/` directory with:
- Unit tests (no network, full suite < 5 s)
- Integration tests gated via `@pytest.mark.integration` (live URLs; opt-in)
- Acceptance-gate tests mapped to `docs/superpowers/specs/2026-05-03-scraping-design.md` §9.5

Run the full suite from a skill's root:
```bash
cd skills/<name>
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m pytest tests/ -v -m "not integration"
```

## Distribution

The plugin lives at `github:jacefrey/scraping`. Once pushed:

```bash
# Once per user, to register the marketplace:
claude plugin marketplace add jacefrey/scraping

# Then install the plugin:
claude plugin install scraping@scraping
```

After installation, skills are invokable as `scraping:web-fetch`, `scraping:webpage-to-md`, etc.

## Working conventions

### Authoring skills

Always invoke `superpowers:writing-skills` before creating or substantially editing a skill in this repo. It defines the SKILL.md structure, frontmatter requirements, and the subagent-based testing protocol.

### TDD discipline

All non-scaffolding tasks use TDD: failing test first, run to confirm it fails, implement, run to confirm it passes. The Phase A plan (`docs/superpowers/plans/2026-05-04-phase-a.md`) encodes this for every task. Spec compliance + code quality reviews run after each task per `superpowers:subagent-driven-development`.

### Boundary discipline

`docs/superpowers/specs/2026-05-03-scraping-design.md` §1.5 lists what these skills explicitly **will not** implement: stealth fingerprinting, CAPTCHA solving, credential replay, TLS/JA3 impersonation. Sites that block at those layers go to `apify-runner` (paid third-party) or manual triage — never new evasion code here.

## Host constraints

- Target machine: 2017 Intel MacBook Pro, macOS 13.
- Python 3.12 at `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12` (python.org notarized .pkg).
- `requests` and `playwright` installed under that interpreter; Chromium downloaded via `playwright install chromium`.
- `apify-runner` is stdlib-only — no pip deps.

## Model recommendation

Default this repo to **Sonnet 4.6** in `.claude/settings.json`. Upgrade to **Opus 4.7** for sessions involving:

- Authoring or substantially restructuring SKILL.md guidance
- Designing new skills (use `superpowers:brainstorming` first)
- Diagnosing why a skill's behavior drifts from spec

Routine TDD implementation, fix loops, and bundle/test mechanics are appropriate for Haiku 4.5 or Sonnet 4.6.

## Language

All natural-language output in this repo defaults to **en-US**.
