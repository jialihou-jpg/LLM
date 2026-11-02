from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "BACKEND_TIMEOUT",
    "BACKEND_UNAVAILABLE",
    "BACKEND_API_ERROR",
    "BACKEND_INVALID_RESPONSE",
    "INTERNAL_ERROR",
]


@dataclass(frozen=True)
class AppError(Exception):
    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details or {},
            }
        }


class ValidationError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("VALIDATION_ERROR", message, details)


class BackendTimeoutError(AppError):
    def __init__(self, message: str = "Backend request timed out", details: dict[str, Any] | None = None):
        super().__init__("BACKEND_TIMEOUT", message, details)


class BackendUnavailableError(AppError):
    def __init__(self, message: str = "Backend unavailable", details: dict[str, Any] | None = None):
        super().__init__("BACKEND_UNAVAILABLE", message, details)


class BackendApiError(AppError):
    def __init__(self, status_code: int, message: str, details: dict[str, Any] | None = None):
        payload = {"status_code": status_code}
        if details:
            payload.update(details)
        super().__init__("BACKEND_API_ERROR", message, payload)


class BackendInvalidResponseError(AppError):
    def __init__(self, message: str = "Backend returned an invalid response", details: dict[str, Any] | None = None):
        super().__init__("BACKEND_INVALID_RESPONSE", message, details)


class InternalError(AppError):
    def __init__(self, message: str = "Internal error", details: dict[str, Any] | None = None):
        super().__init__("INTERNAL_ERROR", message, details)
