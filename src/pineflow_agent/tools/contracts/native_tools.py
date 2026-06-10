"""OpenAI-compatible native tool schemas for GIS actions."""

from __future__ import annotations

import json
from typing import Any

from pineflow_agent.core.models import ActionPlan
from pineflow_agent.tools.contracts.tool_definitions import action_contracts, openai_tools, tool_schema


def action_from_tool_call(message: dict[str, Any]) -> ActionPlan:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise ValueError("Expected exactly one tool call in LLM response.")
    function = tool_calls[0].get("function") if isinstance(tool_calls[0], dict) else None
    if not isinstance(function, dict):
        raise ValueError("Tool call is missing a function payload.")
    name = str(function.get("name") or "").strip()
    if name not in action_contracts():
        raise ValueError(f"Unsupported tool call action: {name or '<empty>'}.")
    raw_arguments = function.get("arguments") or "{}"
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Tool call arguments are not valid JSON: {raw_arguments[:300]}") from exc
    elif isinstance(raw_arguments, dict):
        arguments = dict(raw_arguments)
    else:
        raise ValueError("Tool call arguments must be a JSON string or object.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool call arguments must decode to a JSON object.")
    arguments.pop("step_status", None)
    return ActionPlan(
        thought=f"Use native function calling action {name}.",
        action=name,
        action_input=arguments,
    )
