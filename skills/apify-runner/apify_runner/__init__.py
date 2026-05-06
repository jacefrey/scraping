"""apify-runner — stdlib-only Apify API client. See SKILL.md."""

from apify_runner.result import ApifyRunResult
from apify_runner.errors import (
    ApifyError, ApifyAuthError, ApifyActorNotFoundError,
    ApifyRunFailedError, ApifyTimeoutError, ApifyBudgetExceededError,
    ApifyDatasetError,
)

__version__ = "0.1.0"


# Sentinel for env_file resolution (spec §7.3). Distinct from None so the
# default ("auto-discover .env walking from CWD") can be told apart from
# explicit "skip discovery, env-vars only" (None).
class _EnvAutodiscoverSentinel:
    def __repr__(self) -> str:
        return "ENV_AUTODISCOVER"

    def __bool__(self) -> bool:  # truthy so callers don't accidentally treat as None
        return True


ENV_AUTODISCOVER = _EnvAutodiscoverSentinel()

# `run` imported here for public API; defined in runner.py to avoid
# load-order issues (runner imports from result/errors/client/config/env).
from apify_runner.runner import run  # noqa: E402

__all__ = [
    "run",
    "ApifyRunResult", "ApifyError", "ApifyAuthError",
    "ApifyActorNotFoundError", "ApifyRunFailedError",
    "ApifyTimeoutError", "ApifyBudgetExceededError",
    "ApifyDatasetError", "ENV_AUTODISCOVER", "__version__",
]
