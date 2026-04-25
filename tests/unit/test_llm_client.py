"""Unit tests for OpenAIClient."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import openai
import pytest

from src.agent.llm_client import LLMError, LLMResponse, OpenAIClient, ToolCall


def _make_completion(content: str | None, tool_calls: list[dict[str, Any]] | None = None) -> MagicMock:
    """Build a mock openai ChatCompletion object."""
    message = MagicMock()
    message.content = content
    if tool_calls:
        tcs = []
        for tc in tool_calls:
            m = MagicMock()
            m.id = tc["id"]
            m.function.name = tc["name"]
            m.function.arguments = json.dumps(tc["args"])
            tcs.append(m)
        message.tool_calls = tcs
    else:
        message.tool_calls = None

    choice = MagicMock()
    choice.message = message

    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def client() -> OpenAIClient:
    return OpenAIClient(api_key="test-key", model="gpt-4o")


def test_simple_text_response(client: OpenAIClient) -> None:
    completion = _make_completion("Hello!")
    with patch.object(client._client.chat.completions, "create", return_value=completion):
        response = client.chat([{"role": "user", "content": "hi"}], [])

    assert isinstance(response, LLMResponse)
    assert response.content == "Hello!"
    assert response.tool_calls == []


def test_tool_call_response(client: OpenAIClient) -> None:
    completion = _make_completion(
        None,
        [{"id": "tc1", "name": "slack_list_channels", "args": {}}],
    )
    with patch.object(client._client.chat.completions, "create", return_value=completion):
        response = client.chat([{"role": "user", "content": "list channels"}], [])

    assert response.content is None
    assert len(response.tool_calls) == 1
    tc = response.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.id == "tc1"
    assert tc.name == "slack_list_channels"
    assert tc.args == {}


def test_openai_error_raises_llm_error(client: OpenAIClient) -> None:
    with patch.object(
        client._client.chat.completions,
        "create",
        side_effect=openai.BadRequestError(
            message="bad", response=MagicMock(), body={}
        ),
    ):
        with pytest.raises(LLMError):
            client.chat([], [])


def test_rate_limit_retry_then_success(client: OpenAIClient) -> None:
    """RateLimitError on first call, success on second — tenacity retries."""
    completion = _make_completion("ok")
    call_count = 0

    def side_effect(**kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise openai.RateLimitError(
                message="rate limit", response=MagicMock(), body={}
            )
        return completion

    with patch.object(client._client.chat.completions, "create", side_effect=side_effect):
        response = client.chat([], [])

    assert response.content == "ok"
    assert call_count == 2
