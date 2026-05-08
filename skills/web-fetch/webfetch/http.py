"""Requests-based HTTP fetch path (spec §4.1, §4.2)."""
from __future__ import annotations
import hashlib
import time
from typing import Any
import requests
from webfetch._clock import _clock
from webfetch.result import FetchResult, FetchError
from webfetch.detect import classify_content_type, is_challenge_page

_NON_RETRY_STATUS_CATEGORY = {
    401: "auth_required",
    403: "blocked",      # may be upgraded to bot_challenge by the challenge-page check below
    404: "not_found",
    410: "not_found",
    451: "legal_restriction",
}


def _charset_from_content_type(resp: requests.Response) -> str | None:
    """Return the explicit charset from Content-Type, or None if absent.

    `requests` defaults `resp.encoding` to ISO-8859-1 when the server omits
    a charset parameter — wrong for most modern UTF-8 sites. We only trust
    the encoding when the server explicitly declared it.
    """
    ct = resp.headers.get("Content-Type", "")
    if "charset=" in ct.lower():
        return resp.encoding
    return None


# TODO A.1.11: when HostPoliteness lands, accept a long-lived Session
# parameter so cookie state and connection pooling are reused per host.
def _do_get(url: str, *, timeout: float, headers: dict[str, str],
            allow_redirects: bool, max_redirects: int) -> requests.Response:
    """Wrapper around requests.get — kept tiny so tests can patch this single
    seam instead of the whole `requests` package."""
    s = requests.Session()
    s.max_redirects = max_redirects
    return s.get(url, timeout=timeout, headers=headers,
                 allow_redirects=allow_redirects)


def _do_head(url: str, *, timeout: float, headers: dict[str, str],
             max_redirects: int) -> requests.Response:
    """HEAD pre-flight wrapper. Failure here is non-fatal — caller catches
    and falls through to GET (spec §4.2 step 2). max_redirects matches
    the GET path for consistency."""
    s = requests.Session()
    s.max_redirects = max_redirects
    return s.head(url, timeout=timeout, headers=headers, allow_redirects=True)


def http_fetch(url: str, *, cfg: dict[str, Any]) -> FetchResult:
    fc = cfg["fetch"]
    started = _clock()
    headers = {"User-Agent": fc["user_agent"]}

    network_retries = fc["network_retries"]
    timeout_retries = fc["http_timeout_retries"]
    backoff_network = [1, 3, 9]   # spec §4.3
    backoff_timeout = [2, 6, 18]
    backoff_429_default = 5

    network_attempt = 0
    timeout_attempt = 0
    rate_limit_attempt = 0
    server_error_attempt = 0
    SERVER_ERROR_RETRIES = 1  # spec §4.3: 1 retry after 5 s
    SERVER_ERROR_BACKOFF_DEFAULT = 5

    # Spec §4.2 step 2: optional HEAD pre-flight to get cheap content-type hint.
    # HEAD is a hint only — never poison the result. Servers that block HEAD
    # or networks that fail must fall through silently to the GET path.
    head_content_type: str | None = None
    if fc["use_head"]:
        try:
            h = _do_head(url, timeout=fc["head_timeout_s"], headers=headers,
                         max_redirects=fc["max_redirects"])
            if 200 <= h.status_code < 400:
                head_content_type = h.headers.get("Content-Type")
        except Exception:
            head_content_type = None

    resp = None
    while True:
        try:
            resp = _do_get(
                url,
                timeout=fc["http_timeout_s"],
                headers=headers,
                allow_redirects=True,
                max_redirects=fc["max_redirects"],
            )
        # A.1.7: ConnectTimeout/ConnectionError use network_retries;
        # ReadTimeout uses http_timeout_retries. Most-specific first.
        except requests.exceptions.ConnectTimeout as e:
            if network_attempt < network_retries:
                # Clamps at last entry — no unbounded growth if user sets retries > len(backoff).
                time.sleep(backoff_network[min(network_attempt, len(backoff_network) - 1)])
                network_attempt += 1
                continue
            raise FetchError("network", f"connect timeout on {url}: {e}") from e
        except requests.exceptions.ReadTimeout as e:
            if timeout_attempt < timeout_retries:
                time.sleep(backoff_timeout[min(timeout_attempt, len(backoff_timeout) - 1)])
                timeout_attempt += 1
                continue
            raise FetchError("timeout", f"HTTP read timeout on {url}") from e
        except requests.exceptions.TooManyRedirects as e:
            raise FetchError("redirect_loop", f"redirect loop on {url}") from e
        except requests.exceptions.ConnectionError as e:
            if network_attempt < network_retries:
                time.sleep(backoff_network[min(network_attempt, len(backoff_network) - 1)])
                network_attempt += 1
                continue
            raise FetchError("network", f"network failure on {url}: {e}") from e
        except requests.exceptions.Timeout as e:
            # Defensive catch: no current `requests` subclass besides ConnectTimeout
            # and ReadTimeout reaches here. Belt-and-suspenders for future-proofing.
            if timeout_attempt < timeout_retries:
                time.sleep(backoff_timeout[min(timeout_attempt, len(backoff_timeout) - 1)])
                timeout_attempt += 1
                continue
            raise FetchError("timeout", f"HTTP timeout on {url}") from e

        # 429 retry: independent counter, reuses network_retries as the ceiling.
        # Independent so a session can exhaust both network retries and rate-limit
        # retries without one starving the other.
        # 429 with Retry-After honoring (preserves A.1.6's 408/425/429 mapping).
        if resp.status_code == 429:
            if rate_limit_attempt < network_retries and fc["politeness"]["respect_retry_after"]:
                ra_header = resp.headers.get("Retry-After")
                try:
                    delay = min(int(ra_header), fc["politeness"]["max_retry_after_s"]) \
                        if ra_header is not None else backoff_429_default
                except ValueError:
                    # TODO: RFC 7231 also allows HTTP-date format for Retry-After
                    # (e.g., "Wed, 21 Oct 2026 07:28:00 GMT"); int() raises ValueError
                    # on that. Parse with email.utils.parsedate_to_datetime if needed.
                    delay = backoff_429_default
                time.sleep(delay)
                rate_limit_attempt += 1
                continue
            # Fall through to non-retry rate_limit raise below.

        # Non-retry status mapping (preserves A.1.6's 408/425/429 + 401/403/404/410/451).
        if resp.status_code in (408, 425, 429):
            raise FetchError("rate_limit", f"{resp.status_code} on {url}",
                             http_status=resp.status_code,
                             retry_after=resp.headers.get("Retry-After"))
        if resp.status_code in _NON_RETRY_STATUS_CATEGORY:
            cat = _NON_RETRY_STATUS_CATEGORY[resp.status_code]
            raise FetchError(cat, f"{resp.status_code} on {url}",
                             http_status=resp.status_code)
        if 500 <= resp.status_code < 600:
            if (server_error_attempt < SERVER_ERROR_RETRIES
                    and fc["politeness"]["respect_retry_after"]):
                # 503 typically carries Retry-After when load-shed; other 5xx don't.
                ra_header = resp.headers.get("Retry-After")
                try:
                    delay = (
                        min(int(ra_header), fc["politeness"]["max_retry_after_s"])
                        if ra_header is not None
                        else SERVER_ERROR_BACKOFF_DEFAULT
                    )
                except ValueError:
                    # TODO: RFC 7231 also allows HTTP-date format for Retry-After.
                    delay = SERVER_ERROR_BACKOFF_DEFAULT
                time.sleep(delay)
                server_error_attempt += 1
                continue
            raise FetchError("server_error", f"{resp.status_code} on {url}",
                             http_status=resp.status_code)
        break

    # Spec §4.3: parse_safety caps. max_response_bytes is a Content-Length
    # pre-check (best effort — bails on cooperative servers before reading
    # the body); max_decoded_bytes guards the actual buffered size after
    # requests has auto-decompressed transfer encoding. With the current
    # non-streaming GET, the body is already in memory by the time _do_get
    # returns, so these caps are post-hoc safety rails rather than OOM
    # prevention. Switching to streaming would harden them further; deferred.
    ps = fc["parse_safety"]
    cl_header = resp.headers.get("Content-Length")
    if cl_header is not None:
        try:
            cl = int(cl_header)
        except ValueError:
            cl = None
        if cl is not None and cl > ps["max_response_bytes"]:
            raise FetchError(
                "response_too_large",
                f"Content-Length {cl} exceeds max_response_bytes "
                f"{ps['max_response_bytes']} on {url}",
                http_status=resp.status_code,
                content_length=cl,
                max_response_bytes=ps["max_response_bytes"],
            )

    completed = _clock()
    body = resp.content
    if len(body) > ps["max_decoded_bytes"]:
        raise FetchError(
            "decoded_body_too_large",
            f"decoded body {len(body)} exceeds max_decoded_bytes "
            f"{ps['max_decoded_bytes']} on {url}",
            http_status=resp.status_code,
            decoded_bytes=len(body),
            max_decoded_bytes=ps["max_decoded_bytes"],
        )

    # Apply magic-byte / suffix / HEAD classification (spec §4.2 step 3).
    # Single fetch only — no second GET. We peek the first 1KB of the
    # already-received body. The HEAD path lands in A.1.10.
    # Empty body is falsy — skip magic-byte check and let the GET header win.
    peek = body[:1024] if body else None
    ct, src = classify_content_type(
        url=url,
        head_content_type=head_content_type,
        peek_bytes=peek,
        get_content_type=resp.headers.get("Content-Type"),
    )
    if ct is None:
        # classify_content_type returned (None, None): either peek_bytes didn't
        # begin with %PDF, or the server sent no Content-Type at all.
        # Fall back to the raw GET header to preserve whatever the server said.
        ct = resp.headers.get("Content-Type")
        src = "get_header" if ct else None

    # redirect_chain is empty when no 3xx redirects occurred. URL normalization
    # by the server (e.g., adding a trailing slash) without a 3xx is signaled
    # by `final_url != requested_url`, NOT by a non-empty redirect_chain.
    redirect_chain = [h.url for h in resp.history] if resp.history else []
    if redirect_chain and redirect_chain[0] != url:
        redirect_chain = [url] + redirect_chain

    sha = hashlib.sha256(body).hexdigest()

    # Spec §4.2 step 5: HTML response — check for challenge markers BEFORE returning.
    # Cloudflare/DataDome/PerimeterX detection runs on raw HTML (preserves <script> tags
    # so markers like __cf_chl_jschl_tk__ stay visible). See is_challenge_page() in detect.py.
    is_html = (ct or "").lower().startswith("text/html")
    if is_html:
        title_match, marker = is_challenge_page(
            body,
            http_status=resp.status_code,
            extra_markers=fc["detection"]["challenge_markers"],
        )
        if title_match or marker is not None:
            if fc["return_blocked_content"]:
                # Surface the partial FetchResult so the caller can inspect.
                return FetchResult(
                    requested_url=url,
                    final_url=resp.url,
                    redirect_chain=redirect_chain,
                    started_at=started,
                    completed_at=completed,
                    content=body,
                    content_type=ct,
                    content_type_source=src,
                    encoding=_charset_from_content_type(resp),
                    content_length_bytes=len(body),
                    content_hash_sha256=sha,
                    http_status=resp.status_code,
                    fetch_method="http",
                    error_category="bot_challenge",
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    etag=resp.headers.get("etag"),
                    last_modified=resp.headers.get("last-modified"),
                )
            raise FetchError(
                "bot_challenge",
                f"challenge page detected on {url}",
                title_match=title_match,
                marker=marker,
            )

    return FetchResult(
        requested_url=url,
        final_url=resp.url,
        redirect_chain=redirect_chain,
        started_at=started,
        completed_at=completed,
        content=body,
        content_type=ct,
        content_type_source=src,
        encoding=_charset_from_content_type(resp),
        content_length_bytes=len(body),
        content_hash_sha256=sha,
        http_status=resp.status_code,
        fetch_method="http",
        error_category=None,
        headers={k.lower(): v for k, v in resp.headers.items()},
        etag=resp.headers.get("etag"),
        last_modified=resp.headers.get("last-modified"),
    )
