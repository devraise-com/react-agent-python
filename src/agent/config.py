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
    log_file: str = ""

    # Agent
    max_agent_steps: int = Field(default=20, gt=0)
    current_user: str = ""
    data_dir: Path = Path("data")
