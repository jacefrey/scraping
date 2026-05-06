"""Pagination tests for _paginated_dataset_items (spec §9.5).

Regression coverage for the multi-page concatenation behavior. The runner.py
test_run_happy.py exercises the integration end-to-end with a single mocked
generator; this file tests the pagination primitive directly to lock the
contract.
"""
from unittest.mock import patch
from apify_runner.client import _paginated_dataset_items


def test_paginate_concatenates_three_pages():
    """3 pages: 1000 + 1000 + 350 items → 2350 total, in order."""
    pages = [
        [{"i": j} for j in range(1000)],
        [{"i": j} for j in range(1000, 2000)],
        [{"i": j} for j in range(2000, 2350)],  # short final page signals end
    ]
    page_iter = iter(pages)

    def fake_request(url, **kwargs):
        try:
            return next(page_iter)
        except StopIteration:
            return []

    with patch("apify_runner.client._request", side_effect=fake_request):
        items = list(_paginated_dataset_items(
            "https://api.apify.com/v2", dataset_id="ds-x",
            token="tok", limit=1000,
        ))
    assert len(items) == 2350
    assert items[0] == {"i": 0}
    assert items[-1] == {"i": 2349}


def test_paginate_empty_dataset():
    """First page is empty → iterator yields nothing, no further requests."""
    with patch("apify_runner.client._request", return_value=[]):
        items = list(_paginated_dataset_items(
            "https://api.apify.com/v2", dataset_id="ds-x",
            token="tok", limit=1000,
        ))
    assert items == []


def test_paginate_stops_when_short_page():
    """A single short page (less than limit) signals end without re-fetch."""
    request_calls = []

    def fake_request(url, **kwargs):
        request_calls.append(url)
        return [{"i": 0}, {"i": 1}, {"i": 2}]  # 3 items < limit=10

    with patch("apify_runner.client._request", side_effect=fake_request):
        items = list(_paginated_dataset_items(
            "https://api.apify.com/v2", dataset_id="ds-x",
            token="tok", limit=10,
        ))
    assert len(items) == 3
    # Should have made exactly one request — short page ended pagination.
    assert len(request_calls) == 1


def test_paginate_non_list_response_returns_empty():
    """If Apify returns a non-list (error format), iteration ends gracefully."""
    with patch("apify_runner.client._request", return_value={"error": "oops"}):
        items = list(_paginated_dataset_items(
            "https://api.apify.com/v2", dataset_id="ds-x",
            token="tok", limit=1000,
        ))
    assert items == []
