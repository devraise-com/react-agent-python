"""Application configuration loaded from environment variables / .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Mock service error injection
    mock_error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    mock_force_error: str = ""  # e.g. "slack:rate_limit"

    # Logging
    log_level: str = "INFO"
    log_file: str = "agent.log"
    runtime_dir: Path = Path("runtime")
    environment: str = "dev"
    agent_version: str = "0.1.0"
    session_id: str = ""
    enable_audit_log: bool = True
    audit_log_file: str = "audit_events.jsonl"

    # OpenTelemetry tracing
    enable_tracing: bool = False
    tracing_service_name: str = "react-agent-python"
    tracing_exporter: str = "file"  # file | console | otlp
    tracing_file: str = "traces.jsonl"
    tracing_otlp_endpoint: str = ""  # e.g. http://localhost:4318/v1/traces

    # Agent
    max_agent_steps: int = Field(default=20, gt=0)
    current_user: str = ""
    data_dir: Path = Path("data")

    # Cost accounting (USD per 1M tokens)
    cost_input_per_million_tokens: float = Field(default=5.0, ge=0.0)
    cost_output_per_million_tokens: float = Field(default=15.0, ge=0.0)
    cost_cached_input_per_million_tokens: float = Field(default=1.25, ge=0.0)
