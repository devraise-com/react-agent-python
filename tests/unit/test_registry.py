"""Unit tests for ToolRegistry."""

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from src.tools.base import ToolError
from src.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


def test_register_and_dispatch(registry: ToolRegistry) -> None:
    @registry.register
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    result = registry.dispatch("add", {"a": 1, "b": 2})
    assert result == 3


def test_schemas_include_registered_tool(registry: ToolRegistry) -> None:
    @registry.register
    def greet(name: str) -> str:
        """Greet someone."""
        return f"Hello {name}"

    schemas = registry.schemas()
    assert len(schemas) == 1
    fn_schema = schemas[0]["function"]
    assert fn_schema["name"] == "greet"
    assert fn_schema["description"] == "Greet someone."
    assert "name" in fn_schema["parameters"]["properties"]
    assert "name" in fn_schema["parameters"]["required"]


def test_optional_param_not_in_required(registry: ToolRegistry) -> None:
    @registry.register
    def say(text: str, loud: bool = False) -> str:
        """Say something."""
        return text.upper() if loud else text

    schemas = registry.schemas()
    required = schemas[0]["function"]["parameters"]["required"]
    assert "text" in required
    assert "loud" not in required


def test_list_param_schema(registry: ToolRegistry) -> None:
    @registry.register
    def batch(items: list[str]) -> int:
        """Count items."""
        return len(items)

    props = registry.schemas()[0]["function"]["parameters"]["properties"]
    assert props["items"]["type"] == "array"
    assert props["items"]["items"]["type"] == "string"


def test_dispatch_unknown_tool_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="Unknown tool"):
        registry.dispatch("ghost", {})


def test_dispatch_wraps_exception_as_tool_error(registry: ToolRegistry) -> None:
    @registry.register
    def boom() -> None:
        """Boom."""
        raise ValueError("explosion")

    with pytest.raises(ToolError, match="explosion"):
        registry.dispatch("boom", {})


def test_multiple_tools_in_registry(registry: ToolRegistry) -> None:
    @registry.register
    def tool_a() -> str:
        """A."""
        return "a"

    @registry.register
    def tool_b() -> str:
        """B."""
        return "b"

    assert len(registry.schemas()) == 2
    assert registry.dispatch("tool_a", {}) == "a"
    assert registry.dispatch("tool_b", {}) == "b"


def test_optional_string_param_schema(registry: ToolRegistry) -> None:
    @registry.register
    def search(query: str, channel: str | None = None) -> list[str]:
        """Search."""
        return []

    props = registry.schemas()[0]["function"]["parameters"]["properties"]
    assert props["query"]["type"] == "string"
    assert props["channel"]["type"] == "string"
    required = registry.schemas()[0]["function"]["parameters"]["required"]
    assert "query" in required
    assert "channel" not in required


def test_dispatch_validates_params_model(registry: ToolRegistry) -> None:
    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        text: str
        repeat: int

    class Result(BaseModel):
        model_config = ConfigDict(extra="forbid")
        ok: bool
        output: str

    @registry.register(params_model=Params, result_model=Result)
    def echo(text: str, repeat: int) -> dict[str, Any]:
        return {"ok": True, "output": text * repeat}

    result = registry.dispatch("echo", {"text": "a", "repeat": 3})
    assert result["output"] == "aaa"

    with pytest.raises(ToolError, match="repeat"):
        registry.dispatch("echo", {"text": "a", "repeat": "bad"})


def test_dispatch_validates_result_model(registry: ToolRegistry) -> None:
    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: str

    class Result(BaseModel):
        model_config = ConfigDict(extra="forbid")
        ok: bool
        output: str

    @registry.register(params_model=Params, result_model=Result)
    def broken(value: str) -> dict[str, Any]:
        return {"ok": True, "wrong": value}

    with pytest.raises(ToolError, match="output"):
        registry.dispatch("broken", {"value": "x"})
