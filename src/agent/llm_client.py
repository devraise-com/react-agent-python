"""OpenAI LLM client with retry/backoff and typed response objects."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@dataclass
class ToolCall:
    """A single tool-call requested by the model."""

    id: str  # tool_call_id — required when sending tool results back
    name: str
    args: dict[str, Any]


@dataclass
class LLMResponse:
    """Typed wrapper around an OpenAI chat completion response."""

    content: str | None  # None when the model goes straight to tool_calls
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(Exception):
    """Raised when the LLM call fails after all retries."""


class LLMClient(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Send a chat request and return a typed response."""


class OpenAIClient(LLMClient):
    """OpenAI implementation with exponential-backoff retry."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    @retry(
        retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        try:
            kwargs: dict[str, Any] = {"model": self._model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = self._client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            tool_calls: list[ToolCall] = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            args=json.loads(tc.function.arguments),
                        )
                    )

            return LLMResponse(content=message.content, tool_calls=tool_calls)

        except (openai.RateLimitError, openai.APITimeoutError):
            raise  # let tenacity handle retries
        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc
