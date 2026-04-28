"""Shared types for the tools layer."""

from typing import Any


class ToolError(Exception):
    """Raised by the registry when a tool call fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "tool_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload
