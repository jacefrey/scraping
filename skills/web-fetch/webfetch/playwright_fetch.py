"""Playwright path — Chromium launch + page.content() (spec §4.2 step 7, §4.4)."""
from __future__ import annotations
import hashlib
from typing import Any
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
from webfetch._clock import _clock
from webfetch.result import FetchResult, FetchError


def _frame_navigation_count(page) -> int:
    """Hook — count of frame navigations seen so far. Test seam.

    The implementation increments a counter inside the page-context
    callback (`_on_frame_nav`). Tests can patch this function to force
    a return value (e.g., to exercise the redirect-loop branch without
    setting up a real frame-navigation chain).
    """
    return getattr(page, "_wf_nav_count", 0)


def playwright_fetch(url: str, *, cfg: dict[str, Any]) -> FetchResult:
    pw_cfg = cfg["fetch"]["playwright"]
    started = _clock()
    redirects: list[str] = [url]
    page = None  # ensure defined for the post-block FetchResult call
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=pw_cfg["headless"])
            context = browser.new_context(
                user_agent=cfg["fetch"]["user_agent"],
            )
            page = context.new_page()

            # Track frame navigations for redirect-loop detection.
            page._wf_nav_count = 0  # type: ignore[attr-defined]

            def _on_frame_nav(frame):
                if frame == page.main_frame:
                    page._wf_nav_count += 1  # type: ignore[attr-defined]
                    redirects.append(frame.url)
                    if _frame_navigation_count(page) > pw_cfg["max_redirects"]:
                        raise FetchError(
                            "redirect_loop",
                            f"Playwright redirect loop on {url}",
                        )

            try:
                page.on("framenavigated", _on_frame_nav)
            except Exception:
                # Mock pages may not support .on(); ignore for tests.
                pass

            page.goto(url, timeout=pw_cfg["timeout_s"] * 1000,
                      wait_until=pw_cfg["wait_for"])
            if pw_cfg["wait_for_selector"]:
                page.wait_for_selector(
                    pw_cfg["wait_for_selector"],
                    timeout=pw_cfg["timeout_s"] * 1000,
                )
            if _frame_navigation_count(page) > pw_cfg["max_redirects"]:
                raise FetchError(
                    "redirect_loop",
                    f"Playwright redirect loop on {url}",
                )
            html_str = page.content()
            final_url = page.url
            browser.close()
    except PWTimeoutError as e:
        raise FetchError("timeout", f"Playwright timeout on {url}") from e
    except FetchError:
        raise
    except Exception as e:
        # Distinguish browser-not-installed vs. generic launch failure.
        msg = str(e)
        if "Executable doesn't exist" in msg or "BrowserType.launch" in msg:
            raise FetchError(
                "playwright_unavailable",
                "Playwright browser not installed. Run: "
                "python3.12 -m pip install --user playwright "
                "&& playwright install chromium",
            ) from e
        raise

    completed = _clock()
    body = html_str.encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    # spec §4.1: redirect_chain is empty when no redirect occurred.
    # Playwright's framenavigated event fires for the initial goto AND each
    # subsequent main-frame navigation, so `redirects` contains the seed URL
    # plus all observed navigations. We coalesce it into the same shape
    # http_fetch produces: empty when final_url == requested_url, otherwise
    # the requested URL prepended + intermediate hops, with the final URL
    # trimmed (already exposed via final_url).
    if final_url == url:
        redirect_chain: list[str] = []
    else:
        hops = list(redirects)
        if not hops or hops[0] != url:
            hops = [url] + hops
        if hops and hops[-1] == final_url:
            hops = hops[:-1]
        redirect_chain = hops

    return FetchResult(
        requested_url=url,
        final_url=final_url,
        redirect_chain=redirect_chain,
        started_at=started,
        completed_at=completed,
        content=body,
        content_type="text/html; charset=utf-8",
        content_type_source="playwright_render",
        encoding="utf-8",
        content_length_bytes=len(body),
        content_hash_sha256=sha,
        http_status=200,
        fetch_method="playwright",
        error_category=None,
        headers={},
        playwright_details={
            "wait_strategy": pw_cfg["wait_for"],
            "wait_for_selector": pw_cfg["wait_for_selector"],
            "frame_nav_count": _frame_navigation_count(page),
        },
    )
