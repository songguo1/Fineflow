"""Provider adapters for model-native GIS tool calling.

The executor should receive a normalized ActionPlan and not care whether a
provider uses OpenAI-style tool_calls, legacy function_call, or a slightly
different tool_choice default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pineflow_agent.core.models import ActionPlan
from pineflow_agent.tools.contracts.native_tools import action_from_tool_call


class ModelAdapterError(RuntimeError):
    """Raised when a provider response cannot be normalized to an ActionPlan."""


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    @property
    def value(self) -> str:
        return f"{self.provider}/{self.model}" if self.provider else self.model


class OpenAICompatibleToolAdapter:
    """Normalize OpenAI-compatible chat-completion tool calls."""

    provider: str = "openai-compatible"
    default_tool_choice: Any = "required"
    drop_tool_params = {"tools", "tool_choice", "parallel_tool_calls", "response_format"}

    def __init__(self, *, provider: str = "", model: str = "") -> None:
        self.model_ref = ModelRef(provider=provider or self.provider, model=model)

    def build_tool_payload(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        temperature: float,
        extra_params: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "tools": list(tools),
            "tool_choice": extra_params.get("tool_choice", self.default_tool_choice),
            "parallel_tool_calls": False,
        }
        payload.update(
            {
                key: value
                for key, value in extra_params.items()
                if key not in self.drop_tool_params
            }
        )
        return payload

    def parse_tool_action(self, response: dict[str, Any]) -> ActionPlan:
        choice = self._first_choice(response)
        message = self._choice_message(choice)
        normalized = self._normalize_message(message)
        try:
            return action_from_tool_call(normalized)
        except Exception as exc:
            raise ModelAdapterError(self._diagnostic_message(choice, message, str(exc))) from exc

    @staticmethod
    def _first_choice(response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelAdapterError(f"LLM response has no choices: {_preview(response)}")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ModelAdapterError(f"LLM response choice is not an object: {_preview(choice)}")
        return choice

    @staticmethod
    def _choice_message(choice: dict[str, Any]) -> dict[str, Any]:
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelAdapterError(f"LLM response choice has no message: {_preview(choice)}")
        return message

    @staticmethod
    def _normalize_message(message: dict[str, Any]) -> dict[str, Any]:
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            if len(tool_calls) <= 1:
                return message
            names = [
                str(dict(dict(call).get("function") or {}).get("name") or "<unknown>")
                for call in tool_calls
                if isinstance(call, dict)
            ]
            raise ModelAdapterError(
                "Model returned multiple tool calls, but PineFlow allows exactly one GIS tool action per turn. "
                f"tool_call_count={len(tool_calls)}; tools={', '.join(names) or '<unknown>'}"
            )
        function_call = message.get("function_call")
        if isinstance(function_call, dict):
            normalized = dict(message)
            normalized["tool_calls"] = [{"type": "function", "function": function_call}]
            return normalized
        return message

    def _diagnostic_message(self, choice: dict[str, Any], message: dict[str, Any], reason: str) -> str:
        finish_reason = str(choice.get("finish_reason") or "")
        content = str(message.get("content") or "")
        return (
            f"{self.model_ref.value} did not return a usable native tool call: {reason}. "
            f"finish_reason={finish_reason or '<empty>'}; "
            f"message_keys={sorted(str(key) for key in message.keys())}; "
            f"content_preview={content[:200] or '<empty>'}"
        )


class AutoToolChoiceAdapter(OpenAICompatibleToolAdapter):
    """Adapter for providers that reject tool_choice='required'."""

    default_tool_choice: Any = "auto"

    def build_tool_payload(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        temperature: float,
        extra_params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = super().build_tool_payload(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            temperature=temperature,
            extra_params=extra_params,
        )
        payload.pop("parallel_tool_calls", None)
        return payload


def adapter_for_provider(*, provider: str, model: str, base_url: str = "") -> OpenAICompatibleToolAdapter:
    normalized = _normalize_provider(provider=provider, model=model, base_url=base_url)
    if normalized in {"deepseek", "qwen", "dashscope", "glm", "zhipu"}:
        return AutoToolChoiceAdapter(provider=normalized, model=model)
    return OpenAICompatibleToolAdapter(provider=normalized, model=model)


def _normalize_provider(*, provider: str, model: str, base_url: str) -> str:
    explicit = str(provider or "").strip().lower()
    if explicit:
        return explicit
    if "/" in str(model or ""):
        return str(model).split("/", 1)[0].strip().lower()
    url = str(base_url or "").lower()
    for token in ("deepseek", "dashscope", "qwen", "zhipu", "glm", "openrouter", "openai"):
        if token in url:
            return token
    return "openai-compatible"


def _preview(value: Any, *, limit: int = 500) -> str:
    text = repr(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
