"""FetchResult and FetchError — public types for web-fetch (spec §4.1)."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


ContentTypeSource = Literal[
    "head", "get_header", "magic_bytes", "url_suffix", "playwright_render",
]
FetchMethod = Literal["http", "playwright", "pdf-passthrough"]


@dataclass
class FetchResult:
    # Identity + provenance
    requested_url: str
    final_url: str
    redirect_chain: list[str]
    started_at: datetime
    completed_at: datetime

    # Content
    content: bytes
    content_type: str | None
    content_type_source: ContentTypeSource | None
    encoding: str | None
    content_length_bytes: int
    content_hash_sha256: str | None

    # Network
    http_status: int | None
    fetch_method: FetchMethod
    error_category: str | None
    headers: dict[str, str] = field(default_factory=dict)

    # Conditional-GET signals (v0.2 — accepted-but-ignored in MVP)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False

    # Render-path detail
    playwright_details: dict[str, Any] | None = None

    @property
    def duration_ms(self) -> float:
        return (self.completed_at - self.started_at).total_seconds() * 1000.0

    @property
    def fetched_at(self) -> datetime:
        """Legacy alias for completed_at."""
        return self.completed_at


class FetchError(Exception):
    """Raised on terminal fetch failures. Carries `error_category` (spec §4.3)."""

    def __init__(self, error_category: str, message: str, **context: Any) -> None:
        super().__init__(message)
        self.error_category = error_category
        self.context: dict[str, Any] = context
