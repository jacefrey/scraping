"""Error hierarchy for apify-runner (spec §7.4).

Each subclass carries enough metadata to inspect / clean up the run after
the exception fires — critical when abort_on_timeout=False leaves a paid
run going on Apify."""
from __future__ import annotations


class ApifyError(Exception):
    """Base class for all apify-runner exceptions."""


class ApifyAuthError(ApifyError):
    def __init__(self, message: str, *, env_file_path: str | None = None,
                 mode_octal: int | None = None) -> None:
        super().__init__(message)
        self.env_file_path = env_file_path
        self.mode_octal = mode_octal


class ApifyActorNotFoundError(ApifyError):
    def __init__(self, message: str, *, actor: str) -> None:
        super().__init__(message)
        self.actor = actor


class ApifyRunFailedError(ApifyError):
    def __init__(self, message: str, *, run_id: str, actor: str, status: str,
                 cost_usd_at_failure: float, dataset_id: str | None,
                 error_message: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.actor = actor
        self.status = status
        self.cost_usd_at_failure = cost_usd_at_failure
        self.dataset_id = dataset_id
        self.error_message = error_message


class ApifyTimeoutError(ApifyError):
    def __init__(self, message: str, *, run_id: str, actor: str,
                 status_at_timeout: str, cost_usd_at_timeout: float,
                 dataset_id: str | None, aborted: bool) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.actor = actor
        self.status_at_timeout = status_at_timeout
        self.cost_usd_at_timeout = cost_usd_at_timeout
        self.dataset_id = dataset_id
        self.aborted = aborted


class ApifyBudgetExceededError(ApifyError):
    def __init__(self, message: str, *, run_id: str, actor: str,
                 cost_usd: float, max_cost_usd: float,
                 dataset_id: str | None) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.actor = actor
        self.cost_usd = cost_usd
        self.max_cost_usd = max_cost_usd
        self.dataset_id = dataset_id


class ApifyDatasetError(ApifyError):
    def __init__(self, message: str, *, run_id: str, actor: str,
                 dataset_id: str | None, items_retrieved: int,
                 cause: str) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.actor = actor
        self.dataset_id = dataset_id
        self.items_retrieved = items_retrieved
        self.cause = cause  # "network" | "cap_exceeded" | "parse"
