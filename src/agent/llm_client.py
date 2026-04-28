"""OpenAI LLM client with retry/backoff and typed response objects."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import openai
from tenacity import (
    Retrying,
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
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class LLMResponse:
    """Typed wrapper around an OpenAI chat completion response."""

    content: str | None  # None when the model goes straight to tool_calls
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    retry_count: int = 0


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

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        attempts = 0
        try:
            retrying = Retrying(
                retry=retry_if_exception_type(
                    (openai.RateLimitError, openai.APITimeoutError)
                ),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                stop=stop_after_attempt(4),
                reraise=True,
            )
            response: Any
            for attempt in retrying:
                with attempt:
                    attempts += 1
                    kwargs: dict[str, Any] = {"model": self._model, "messages": messages}
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = "auto"
                    response = self._client.chat.completions.create(**kwargs)

            message = response.choices[0].message
            usage = self._extract_usage(response)

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

            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                usage=usage,
                retry_count=max(attempts - 1, 0),
            )

        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc

    def _extract_usage(self, response: Any) -> LLMUsage:
        usage_obj = getattr(response, "usage", None)
        if usage_obj is None:
            return LLMUsage()
        input_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)

        # SDK shape may vary by API version; handle both object and dict-like payloads.
        cached_tokens = 0
        details = getattr(usage_obj, "prompt_tokens_details", None)
        if details is not None:
            cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
        elif isinstance(usage_obj, dict):
            details_obj = usage_obj.get("prompt_tokens_details", {})
            if isinstance(details_obj, dict):
                cached_tokens = int(details_obj.get("cached_tokens", 0) or 0)

        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )
