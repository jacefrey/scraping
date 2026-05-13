"""Filename collision policy: <domain>__<path_slug>__<short_hash> (spec §5.8)."""
from __future__ import annotations
import hashlib
import re
from urllib.parse import urlparse


_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def _slugify(text: str) -> str:
    """Lowercase, non-word → hyphen, strip leading/trailing hyphens."""
    text = _SLUG_RE.sub("-", text.lower())
    return text.strip("-")


def derive_stem(final_url: str) -> str:
    """Return `<domain>__<path_slug>__<short_hash>` (spec §5.8).

    - domain: host with dots replaced by hyphens (lowercase)
    - path_slug: path slugified (defaults to "root" for "/" or empty)
    - short_hash: first 8 hex chars of sha256(final_url + query_string)
    """
    parsed = urlparse(final_url)
    host = (parsed.hostname or "").lower().replace(".", "-")
    raw_path = parsed.path or ""
    path_slug = _slugify(raw_path) or "root"
    query = parsed.query or ""
    hash_input = (final_url + query).encode("utf-8")
    short_hash = hashlib.sha256(hash_input).hexdigest()[:8]
    return f"{host}__{path_slug}__{short_hash}"
