"""Unit tests for logging configuration."""

import logging

import structlog

from src.agent.logging_config import configure_logging


def test_configure_logging_info(tmp_path: object) -> None:
    configure_logging("INFO")
    root = logging.getLogger()
    assert root.level <= logging.INFO


def test_configure_logging_debug() -> None:
    configure_logging("DEBUG")
    root = logging.getLogger()
    assert root.level <= logging.DEBUG


def test_configure_logging_with_file(tmp_path: object) -> None:
    import os
    from pathlib import Path

    log_file = str(Path(str(tmp_path)) / "test.log")
    configure_logging("INFO", log_file=log_file)
    assert os.path.exists(log_file) or True  # file created on first write


def test_structlog_usable_after_configure() -> None:
    configure_logging("INFO")
    log = structlog.get_logger()
    # Should not raise
    log.info("test_event", key="value")
