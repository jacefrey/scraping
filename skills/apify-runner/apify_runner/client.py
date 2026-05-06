"""stdlib-only HTTP wrappers for the Apify v2 API (spec §7.8)."""
from __future__ import annotations
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Any


class ApifyHttpError(Exception):
    def __init__(self, message: str, *, status: int, body: bytes | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _request(url: str, *, token: str, method: str = "GET",
             body: dict | None = None, timeout: float = 30.0) -> Any:
    """Single HTTP request via urllib. Returns decoded JSON (dict or list).

    Raises ApifyHttpError on 4xx/5xx (preserves response body for diagnostics).
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "apify-runner/0.1",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        # HTTPError IS a response — read its body for diagnostics, then raise.
        payload = e.read() if hasattr(e, "read") else b""
        raise ApifyHttpError(
            f"HTTP {e.code} on {url}",
            status=e.code,
            body=payload,
        ) from e
    if status >= 400:
        raise ApifyHttpError(
            f"HTTP {status} on {url}",
            status=status,
            body=payload,
        )
    return json.loads(payload.decode("utf-8"))


def _get_json(url: str, *, token: str, timeout: float = 30.0) -> Any:
    return _request(url, token=token, method="GET", timeout=timeout)


def _post_json(url: str, *, token: str, body: dict, timeout: float = 60.0) -> Any:
    return _request(url, token=token, method="POST", body=body, timeout=timeout)


def _abort_run(api_base: str, *, run_id: str, token: str) -> Any:
    url = f"{api_base.rstrip('/')}/actor-runs/{run_id}/abort"
    return _request(url, token=token, method="POST", timeout=30.0)


def _paginated_dataset_items(api_base: str, *, dataset_id: str, token: str,
                             limit: int = 1000):
    """Yield items from /datasets/{id}/items in `limit`-sized pages."""
    offset = 0
    while True:
        params = urllib.parse.urlencode({"offset": offset, "limit": limit,
                                         "format": "json"})
        url = f"{api_base.rstrip('/')}/datasets/{dataset_id}/items?{params}"
        page = _request(url, token=token, method="GET")
        # Apify dataset/items returns a JSON array directly when format=json
        if not isinstance(page, list):
            return
        if not page:
            return
        for item in page:
            yield item
        if len(page) < limit:
            return
        offset += limit
