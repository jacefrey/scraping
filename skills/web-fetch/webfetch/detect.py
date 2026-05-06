"""Content-type, thin-shell, and challenge-page detection (spec §4.2)."""
from __future__ import annotations
import re
from urllib.parse import urlparse


def classify_content_type(
    *,
    url: str,
    head_content_type: str | None,
    peek_bytes: bytes | None,
    get_content_type: str | None = None,
) -> tuple[str | None, str | None]:
    """Decide (content_type, content_type_source) from available signals.

    Priority: URL suffix `.pdf` > HEAD content-type > magic bytes > GET header.
    Returns (None, None) if no PDF signal AND peek_bytes were provided
    (caller should then route as HTML / step 5).
    """
    # 1. URL suffix
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return "application/pdf", "url_suffix"

    # 2. HEAD content-type
    if head_content_type:
        ct = head_content_type.split(";")[0].strip().lower()
        if ct == "application/pdf":
            return "application/pdf", "head"

    # 3. Magic bytes
    if peek_bytes is not None:
        if peek_bytes.startswith(b"%PDF"):
            return "application/pdf", "magic_bytes"
        # Not PDF — caller should continue with HTML routing.
        return None, None

    # 4. Fallback: trust the GET header if we got there.
    # Normalize the same way the HEAD branch does — clean MIME type only;
    # charset belongs on FetchResult.encoding (spec §4.1).
    if get_content_type:
        ct = get_content_type.split(";")[0].strip().lower()
        return ct, "get_header"

    # No signal available — caller provided neither peek_bytes nor a GET header.
    # Should not occur in normal orchestration; A.1.6 always provides one.
    return None, None


# Built-in challenge-page markers (spec §4.2 step 5).
# Order matters for documentation, not detection — any match wins.
_BUILTIN_CHALLENGE_MARKERS = (
    b"cf-challenge-running",
    b"__cf_chl_jschl_tk__",
    b"cf-error-overview",
    b"Datadome",
    b"_pxhcaptcha",
)

_CHALLENGE_TITLES = (
    "Just a moment...",
    "Access denied",
    "Attention Required!",
    "Verifying you are human",
    "Please verify you are a human",
)

_FRAMEWORK_MARKERS = (
    b"__NEXT_DATA__",
    b"__INITIAL_STATE__",
    b'id="__next"',
    b'data-reactroot',
    b"You need to enable JavaScript",
)

_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(rb"<[^>]+>")
_SCRIPT_RE = re.compile(rb"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(rb"<style\b.*?</style>", re.IGNORECASE | re.DOTALL)


def is_challenge_page(
    raw_html: bytes,
    http_status: int,
    extra_markers: list[str],
) -> tuple[bool, str | None]:
    """Return (title_matches_challenge, first_body_marker_found).

    Spec §4.2 step 5: must inspect the RAW HTML (preserving <script> tags)
    so that markers like __cf_chl_jschl_tk__ inside scripts stay visible.
    """
    title_match = False
    m = _TITLE_RE.search(raw_html)
    if m:
        try:
            title = m.group(1).decode("utf-8", errors="ignore").strip()
        except Exception:
            title = ""
        if any(t.lower() in title.lower() for t in _CHALLENGE_TITLES):
            title_match = True

    all_markers: list[bytes] = list(_BUILTIN_CHALLENGE_MARKERS) + [
        m.encode("utf-8") for m in extra_markers
    ]
    body_marker: str | None = None
    for marker in all_markers:
        if marker in raw_html:
            body_marker = marker.decode("utf-8", errors="ignore")
            break

    # 403 + body that matches challenge fingerprints — flag aggressively.
    if http_status == 403 and body_marker is not None:
        return True, body_marker

    return title_match, body_marker


def is_thin_shell(raw_html: bytes, http_thin_threshold_bytes: int) -> bool:
    """Spec §4.2 step 6: framework markers checked on raw HTML; text-content
    signal checked on tag-stripped HTML. Byte-count signal is secondary.
    """
    # Framework markers must be checked BEFORE tag stripping
    if any(m in raw_html for m in _FRAMEWORK_MARKERS):
        return True

    # Text-content signal: visible text < 200 chars after stripping
    no_scripts = _SCRIPT_RE.sub(b"", raw_html)
    no_styles = _STYLE_RE.sub(b"", no_scripts)
    text_only = _TAG_RE.sub(b" ", no_styles)
    visible = text_only.decode("utf-8", errors="ignore").split()
    if sum(len(w) for w in visible) < 200 and len(raw_html) > 100:
        return True

    # Byte-count signal: very small responses
    if len(raw_html) < http_thin_threshold_bytes:
        return True

    return False
