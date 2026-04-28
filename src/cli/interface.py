"""Rich-based interactive CLI for the ReAct agent."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule

from src.agent.config import Settings
from src.agent.llm_client import OpenAIClient
from src.agent.logging_config import configure_logging
from src.agent.loop import AgentLoop, StepEvent
from src.mock_services.base import ErrorInjector
from src.mock_services.calendar_service import CALENDAR_DEFAULTS, CalendarService
from src.mock_services.email_service import EMAIL_DEFAULTS, EmailService
from src.mock_services.jira_service import JIRA_DEFAULTS, JiraService
from src.mock_services.persistence import JsonStore
from src.mock_services.slack_service import SLACK_DEFAULTS, SlackService
from src.tools.calendar import register_calendar_tools
from src.tools.email import register_email_tools
from src.tools.jira import register_jira_tools
from src.tools.registry import ToolRegistry
from src.tools.slack import register_slack_tools


def _build_loop(settings: Settings) -> AgentLoop:
    """Wire services → tools → registry → LLM → loop."""
    injector = ErrorInjector(settings.mock_error_rate, settings.mock_force_error)

    slack_svc = SlackService(
        JsonStore(settings.data_dir / "slack.json", SLACK_DEFAULTS), injector
    )
    calendar_svc = CalendarService(
        JsonStore(settings.data_dir / "calendar.json", CALENDAR_DEFAULTS), injector
    )
    jira_svc = JiraService(
        JsonStore(settings.data_dir / "jira.json", JIRA_DEFAULTS), injector
    )
    email_svc = EmailService(
        JsonStore(settings.data_dir / "email.json", EMAIL_DEFAULTS), injector
    )

    registry = ToolRegistry()
    register_slack_tools(slack_svc, registry)
    register_calendar_tools(calendar_svc, registry)
    register_jira_tools(jira_svc, registry)
    register_email_tools(email_svc, registry)

    llm = OpenAIClient(settings.openai_api_key, settings.openai_model)
    return AgentLoop(llm, registry, settings)


class AgentCLI:
    """Interactive REPL that renders ReAct step events with rich formatting."""

    def __init__(self, settings: Settings) -> None:
        log_file = settings.log_file
        if log_file and not Path(log_file).is_absolute():
            log_file = str(settings.runtime_dir / log_file)
        configure_logging(settings.log_level, log_file)
        self._loop = _build_loop(settings)
        self._console = Console()

    def run(self) -> None:
        c = self._console
        c.print(Rule("[bold cyan]ReAct AI Agent[/bold cyan]"))
        c.print(
            "[dim]Connected: Slack · Calendar · Jira · Email  "
            "| Type [bold]quit[/bold] to exit[/dim]\n"
        )

        while True:
            try:
                user_input = c.input("[bold green]You:[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                c.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                c.print("[dim]Goodbye![/dim]")
                break

            self._process(user_input)

    def _process(self, user_input: str) -> None:
        c = self._console
        c.print()
        tool_calls_made: list[StepEvent] = []

        for event in self._loop.run(user_input):
            if event.type == "reasoning" and event.content:
                c.print(f"[dim italic]{event.content}[/dim italic]")

            elif event.type == "tool_call":
                c.print(
                    Panel(
                        Pretty(event.args),
                        title=f"[cyan]⚙  {event.name}[/cyan]",
                        border_style="cyan",
                        expand=False,
                    )
                )
                tool_calls_made.append(event)

            elif event.type == "tool_result":
                c.print(f"  [green]✓[/green] [dim]{event.name} succeeded[/dim]")

            elif event.type == "tool_error":
                c.print(f"  [red]✗[/red] [dim]{event.name}: {event.error}[/dim]")

            elif event.type == "error":
                c.print(f"\n[bold red]Error:[/bold red] {event.error}")

            elif event.type == "final_answer" and event.content:
                c.print()
                c.print(
                    Panel(
                        event.content,
                        title="[bold white]Agent[/bold white]",
                        border_style="white",
                    )
                )

        # Summary of actions taken
        if tool_calls_made:
            c.print()
            c.print("[dim]Actions taken:[/dim]")
            for i, tc in enumerate(tool_calls_made, 1):
                args_str = ", ".join(
                    f"{k}={v!r}" for k, v in (tc.args or {}).items()
                )
                c.print(f"[dim]  {i}. {tc.name}({args_str})[/dim]")

        c.print()
