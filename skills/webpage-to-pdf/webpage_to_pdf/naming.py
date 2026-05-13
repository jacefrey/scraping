"""Filename collision policy (spec §5.8 — re-implemented per §8.1 boundary)."""
from __future__ import annotations
import hashlib
import re
from urllib.parse import urlparse


_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def derive_stem(final_url: str) -> str:
    parsed = urlparse(final_url)
    host = (parsed.hostname or "").lower().replace(".", "-")
    raw_path = parsed.path or ""
    path_slug = _slugify(raw_path) or "root"
    query = parsed.query or ""
    short_hash = hashlib.sha256((final_url + query).encode("utf-8")).hexdigest()[:8]
    return f"{host}__{path_slug}__{short_hash}"
