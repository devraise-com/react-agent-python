"""Shared error types and error-injection logic for all mock services."""

import random
from enum import Enum


class ErrorCode(str, Enum):
    RATE_LIMIT = "rate_limit"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"


class MockServiceError(Exception):
    """Raised by mock services to simulate API errors."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ErrorInjector:
    """Injects errors based on MOCK_ERROR_RATE and MOCK_FORCE_ERROR settings.

    MOCK_ERROR_RATE=0.1  → 10 % random failures on any service call
    MOCK_FORCE_ERROR=slack:rate_limit → next Slack call raises rate_limit
    """

    def __init__(self, error_rate: float, force_error: str) -> None:
        self._error_rate = error_rate
        self._force_error = force_error  # "<service>:<code>" or ""

    def maybe_raise(self, service: str) -> None:
        """Check injection rules; raise MockServiceError if triggered."""
        # Targeted override takes precedence
        if self._force_error:
            parts = self._force_error.split(":", 1)
            if len(parts) == 2 and parts[0] == service:
                # Consume one-shot forced error on first matching call.
                self._force_error = ""
                try:
                    code = ErrorCode(parts[1])
                except ValueError:
                    code = ErrorCode.SERVER_ERROR
                raise MockServiceError(code, f"Forced error [{service}]: {code.value}")

        # Random rate-based injection
        if self._error_rate > 0.0 and random.random() < self._error_rate:
            code = random.choice(list(ErrorCode))
            raise MockServiceError(code, f"Random error [{service}]: {code.value}")
