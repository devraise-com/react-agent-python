"""Email (Gmail) tool wrappers — thin closures around EmailService."""

from typing import Any

from src.mock_services.email_service import EmailService
from src.tools.registry import ToolRegistry


def register_email_tools(service: EmailService, registry: ToolRegistry) -> None:
    """Register all Email tools into the given registry."""

    @registry.register
    def email_send(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send an email.
        to is a list of recipient email addresses.
        cc is an optional list of CC addresses.
        """
        return service.send_email(to, subject, body, cc)

    @registry.register
    def email_search(query: str, folder: str = "inbox") -> dict[str, Any]:
        """Search emails by keyword (matches subject and body).
        folder must be one of: inbox, outbox, all.
        """
        return service.search_email(query, folder)
