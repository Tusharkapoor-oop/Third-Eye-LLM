"""Public error contract."""

from __future__ import annotations

from enum import StrEnum


class ErrCode(StrEnum):
    BAD_INPUT = "bad_input"
    BLOCKED_URL = "blocked_url"
    DNS = "dns_error"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    HTTP = "http_error"
    UNSUPPORTED = "unsupported_type"
    EXTRACT = "extract_failed"
    PROVIDER = "provider_error"
    NO_PROVIDER = "no_provider"
    ROBOTS = "robots_denied"
    BUDGET = "budget_exhausted"
    CACHE = "cache_error"
    INTERNAL = "internal_error"


class WebLensError(Exception):
    """Base error carrying a stable machine code and a short human message."""

    code: ErrCode = ErrCode.INTERNAL

    def __init__(self, message: str, *, code: ErrCode | None = None, retryable: bool = False):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.retryable = retryable

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "error",
            "err": str(self.code),
            "msg": self.message[:300],
            "retry": self.retryable,
        }


class BlockedURLError(WebLensError):
    code = ErrCode.BLOCKED_URL


class FetchError(WebLensError):
    code = ErrCode.HTTP

    def __init__(
        self,
        message: str,
        *,
        code: ErrCode | None = None,
        retryable: bool = False,
        status: int | None = None,
    ):
        super().__init__(message, code=code, retryable=retryable)
        self.status = status


class ProviderError(WebLensError):
    code = ErrCode.PROVIDER


def resolve_budget(
    requested: int | None,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Return an explicit budget, rejecting requests too small for provenance.

    Silently raising a caller's budget would break the promise that ``max_tokens``
    is an upper bound, so values below the documented floor are a bad input.
    """
    if requested is None:
        return max(minimum, min(maximum, default))
    if requested < minimum:
        raise WebLensError(
            f"max_tokens must be >= {minimum} for this tool",
            code=ErrCode.BAD_INPUT,
        )
    return min(maximum, requested)
