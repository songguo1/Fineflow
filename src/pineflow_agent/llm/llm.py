"""LLM clients for the standalone ReAct GIS agent."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol
from urllib import error, request

from pineflow_agent.llm.model_adapters import ModelAdapterError, OpenAICompatibleToolAdapter, adapter_for_provider
from pineflow_agent.core.models import ActionPlan


class LLMClient(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return structured JSON text for resume and compatibility tasks."""

    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return plain text for user-facing narration."""

    def tool_call(self, *, system_prompt: str, user_prompt: str, tools: list[dict[str, Any]]) -> ActionPlan:
        """Return one model-native tool call normalized as an ActionPlan."""


def extract_json_object(text: str) -> str:
    """Extract the most useful JSON object from a model response."""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("LLM returned empty content.")
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    if raw.startswith("{") and raw.endswith("}") and _is_json_object(raw):
        return raw

    candidates = _json_object_candidates(raw)
    if candidates:
        return max(candidates, key=_json_candidate_score)
    if "{" not in raw or "}" not in raw:
        raise ValueError(f"Could not find JSON object in LLM response: {raw[:300]}")
    raise ValueError(f"Could not find a valid JSON object in LLM response: {raw[:300]}")


def _is_json_object(text: str) -> bool:
    try:
        return isinstance(json.loads(text), dict)
    except json.JSONDecodeError:
        return False


def _decode_http_body(body: bytes, *, charset: str | None = "") -> str:
    encodings = [str(charset or "").strip().lower(), "utf-8", "utf-8-sig", "gb18030", "cp1252"]
    seen: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding in seen:
            continue
        seen.add(encoding)
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    starts = [index for index, char in enumerate(text) if char == "{"]
    for start in starts:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    if _is_json_object(candidate):
                        candidates.append(candidate)
                    break
                if depth < 0:
                    break
    return candidates


def _json_candidate_score(candidate: str) -> tuple[int, int]:
    payload = json.loads(candidate)
    keys = set(payload)
    score = 0
    if {"action", "action_input"} <= keys:
        score += 100
    if "steps" in keys:
        score += 90
    if "decision" in keys:
        score += 90
    if "thought" in keys:
        score += 10
    if "message" in keys:
        score += 2
    return score, len(candidate)


class OpenAICompatibleLLM:
    """Small OpenAI-compatible chat completion client.

    Works with providers that expose an OpenAI-compatible /chat/completions API.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        provider: str = "",
        temperature: float = 0.0,
        timeout_seconds: int = 120,
        extra_params: dict[str, Any] | None = None,
        adapter: OpenAICompatibleToolAdapter | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.provider = str(provider or "").strip().lower()
        self.temperature = float(temperature)
        self.timeout_seconds = int(timeout_seconds)
        self.extra_params = dict(extra_params or {})
        if not self.api_key:
            raise ValueError("api_key is required.")
        if not self.model:
            raise ValueError("model is required.")
        if not self.base_url:
            raise ValueError("base_url is required.")
        self.adapter = adapter or adapter_for_provider(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
        )

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }
        payload.update(self.extra_params)
        data = self._post_chat_completion(payload)
        message = self._first_message(data)
        content = str(message.get("content") or "").strip()
        return extract_json_object(content)

    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }
        payload.update(self.extra_params)
        data = self._post_chat_completion(payload)
        message = self._first_message(data)
        return str(message.get("content") or "").strip()

    def tool_call(self, *, system_prompt: str, user_prompt: str, tools: list[dict[str, Any]]) -> ActionPlan:
        payload = self.adapter.build_tool_payload(
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            temperature=self.temperature,
            extra_params=self.extra_params,
        )
        data = self._post_chat_completion(payload)
        try:
            return self.adapter.parse_tool_action(data)
        except ModelAdapterError as exc:
            if not self._should_retry_native_tool_call(response=data):
                raise
            retry_payload = self.adapter.build_tool_payload(
                model=self.model,
                system_prompt=_retry_tool_system_prompt(system_prompt),
                user_prompt=user_prompt,
                tools=tools,
                temperature=self.temperature,
                extra_params=self.extra_params,
            )
            retry_data = self._post_chat_completion(retry_payload)
            try:
                return self.adapter.parse_tool_action(retry_data)
            except ModelAdapterError:
                raise exc

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self._completion_url(),
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        response_charset = ""
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                response_charset = response.headers.get_content_charset() or ""
                response_body = response.read()
        except error.HTTPError as exc:
            error_charset = exc.headers.get_content_charset() if exc.headers else ""
            error_body = _decode_http_body(exc.read(), charset=error_charset)
            raise RuntimeError(f"LLM request failed, HTTP {exc.code}: {error_body[:500]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"LLM connection failed: {exc}") from exc

        return json.loads(_decode_http_body(response_body, charset=response_charset))

    @staticmethod
    def _first_message(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"LLM response has no choices: {data}")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise RuntimeError(f"LLM response choice has no message: {choices[0]}")
        return message

    def _completion_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/chat/completions"

    @staticmethod
    def _should_retry_native_tool_call(*, response: dict[str, Any]) -> bool:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return False
        choice = choices[0] if isinstance(choices[0], dict) else {}
        finish_reason = str(choice.get("finish_reason") or "").strip().lower()
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        if finish_reason != "tool_calls":
            return False
        tool_calls = message.get("tool_calls")
        has_reasoning_only = bool(
            str(message.get("content") or "").strip()
            or str(message.get("reasoning_content") or "").strip()
        )
        if isinstance(tool_calls, list) and len(tool_calls) == 0:
            return has_reasoning_only
        if tool_calls is None:
            return has_reasoning_only
        return False


def _retry_tool_system_prompt(system_prompt: str) -> str:
    addition = (
        "\n\nRetry requirement: your previous response was invalid because it did not contain exactly one usable native tool call. "
        "Return exactly one tool call now. Do not return planning text without a tool call. "
        "If multiple operations are possible, choose only the earliest prerequisite operation."
    )
    return f"{system_prompt}{addition}"
