"""Apify token resolution from .env files (spec §7.3)."""
from __future__ import annotations
import logging
import os
import stat
from pathlib import Path
from typing import Any
from apify_runner import ENV_AUTODISCOVER
from apify_runner.errors import ApifyAuthError

log = logging.getLogger("apify_runner.env")
TOKEN_KEY = "APIFY_API_TOKEN"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if v.startswith(("'", '"')) and v.endswith(v[0]) and len(v) >= 2:
            v = v[1:-1]
        out[k.strip()] = v
    return out


def _walk_to_env_file(start: Path) -> Path | None:
    """Walk up from `start` looking for .env, stopping at first .git/ dir
    or $HOME. Returns the .env path or None."""
    home = Path(os.environ.get("HOME", str(Path.home()))).resolve()
    cur = start.resolve()
    while True:
        candidate = cur / ".env"
        if candidate.is_file():
            return candidate
        if (cur / ".git").is_dir():
            return None  # bounded by git-root; no .env inside the repo
        if cur == home:
            log.info(
                "apify_runner: no git-root found in walk; "
                "APIFY_API_TOKEN must come from os.environ "
                "(boundary was $HOME)"
            )
            return None
        if cur.parent == cur:
            return None
        cur = cur.parent


def _check_permissions(path: Path, strict: bool) -> None:
    """Warn (or raise if strict) on world/group-readable .env."""
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        msg = (f"apify_runner: {path} has loose permissions "
               f"(mode 0o{mode:o}); should be 0o600")
        if strict:
            raise ApifyAuthError(
                f"refusing to read {path} (mode 0o{mode:o}); "
                "set strict_permissions=false to override or chmod 600",
                env_file_path=str(path),
                mode_octal=mode,
            )
        log.warning(msg)


def resolve_apify_token(
    *,
    env_file: Any = ENV_AUTODISCOVER,
    strict_permissions: bool = False,
) -> tuple[str, str]:
    """Resolve APIFY_API_TOKEN per spec §7.3.

    Returns (token, source_description).
    Source is either "os.environ" or the absolute path to the .env used.
    """
    # Sentinel: ENV_AUTODISCOVER (default — walk CWD upward to git-root or $HOME)
    if env_file is ENV_AUTODISCOVER:
        env_path = _walk_to_env_file(Path.cwd())
        if env_path is not None:
            _check_permissions(env_path, strict_permissions)
            data = _parse_env_file(env_path)
            tok = data.get(TOKEN_KEY)
            if tok:
                log.debug("apify_runner: resolved %s from %s", TOKEN_KEY, env_path)
                return tok, str(env_path)
        # Fall through to os.environ
        tok = os.environ.get(TOKEN_KEY)
        if tok:
            return tok, "os.environ"
        raise ApifyAuthError(
            f"{TOKEN_KEY} not found.\n"
            f"Set it in <project>/.env (mode 600) or export it in your shell.\n"
            f"Get a token from https://console.apify.com/account/integrations.",
        )

    # None: skip discovery, env-vars only
    if env_file is None:
        tok = os.environ.get(TOKEN_KEY)
        if tok:
            return tok, "os.environ"
        raise ApifyAuthError(
            f"{TOKEN_KEY} not set in os.environ (env_file=None skips .env discovery).",
        )

    # Explicit Path
    p = Path(env_file)
    if p.is_file():
        _check_permissions(p, strict_permissions)
        data = _parse_env_file(p)
        tok = data.get(TOKEN_KEY)
        if tok:
            return tok, str(p)
    # Fall through to os.environ on missing file or missing key
    tok = os.environ.get(TOKEN_KEY)
    if tok:
        return tok, "os.environ"
    raise ApifyAuthError(
        f"{TOKEN_KEY} not in {p} and not in os.environ.",
        env_file_path=str(p),
    )
