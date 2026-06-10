"""Runtime meta-tool implementations used by the ReAct loop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import Observation
from pineflow_agent.orchestration.resume.export_result_contract import (
    export_result_missing_slots,
    export_result_question,
    export_result_slot_patch_schema,
)
from pineflow_agent.rules.validation import PendingTask
from pineflow_agent.tools.contracts.tool_definitions import canonical_action_for_intent, display_title_for_action


def select_toolkit_observation(tool_disclosure: Any, action_input: dict[str, Any]) -> Observation:
    return tool_disclosure.select_toolkits(action_input)


def inspect_workspace_observation(
    tool_disclosure: Any,
    *,
    state: Any = None,
    action_input: dict[str, Any] | None = None,
    tool_registry: Any = None,
    toolbox: Any = None,
    steps: list[Any] | None = None,
    session_id: str = "",
) -> Observation:
    state_dict = {}
    if state is not None and hasattr(state, "to_dict"):
        state_dict = state.to_dict()
    payload = dict(action_input or {})
    payload["__context"] = _workspace_context(toolbox=toolbox, steps=steps, session_id=session_id)
    return tool_disclosure.inspect_workspace(state_dict, payload, tool_registry)


def suggest_skill_observation(action_input: dict[str, Any], *, default_query: str = "") -> Observation:
    from pineflow_agent.tools.registry.skill_registry import default_skill_registry

    query = str(dict(action_input or {}).get("query") or default_query or "").strip()
    limit = int(dict(action_input or {}).get("limit") or 3)
    registry = default_skill_registry()
    suggestions = registry.suggest(query, limit=limit)
    return Observation(
        status="success",
        message=f"Suggested {len(suggestions)} GIS skill(s).",
        data={
            "query": query,
            "suggested_skills": suggestions,
            "skill_hints": [str(item.get("name") or "") for item in suggestions if str(item.get("name") or "")],
        },
    )


def load_skill_observation(toolbox: Any, action_input: dict[str, Any], tool_disclosure: Any = None) -> Observation:
    from pineflow_agent.tools.registry.skill_registry import default_skill_registry

    name = str(dict(action_input or {}).get("name") or "").strip()
    registry = default_skill_registry()
    meta = registry.get(name)

    if meta is None:
        available = ", ".join(registry.names()) or "(none)"
        return Observation(
            status="failed",
            message=f"Unknown skill '{name}'. Available: {available}.",
            output_layer_id="",
            output_path="",
        )

    workspace = getattr(toolbox, "workspace", None)
    if workspace is None:
        return Observation(
            status="failed",
            message=f"Workspace not available, cannot load skill '{name}'.",
            output_layer_id="",
            output_path="",
        )

    content = registry.read_skill_content(name)
    if not content:
        return Observation(
            status="failed",
            message=f"Skill file not found or empty: resources/skills/{name}.md",
            output_layer_id="",
            output_path="",
        )

    toolkit_names: list[str] = []
    if tool_disclosure is not None and hasattr(tool_disclosure, "select_toolkits"):
        required = list(meta.requires_toolkits)
        missing = [t for t in required if t not in tool_disclosure.active_toolkits]
        if missing:
            result = tool_disclosure.select_toolkits({"toolkits": missing, "reason": f"Skill '{name}' requires these ToolKits"})
            toolkit_names = list(result.data.get("active_toolkits", []))

    return Observation(
        status="success",
        message=f"Loaded skill '{name}'. Its guidance will be available in the next tool selection turn.",
        output_layer_id="",
        output_path="",
        data={
            "skill_name": name,
            "skill_content": content,
            "auto_activated_toolkits": toolkit_names,
        },
    )


def proactive_clarification_observation(action_input: dict[str, Any], *, default_request: str = "") -> Observation:
    payload = dict(action_input or {})
    question = str(payload.get("question") or payload.get("message") or "").strip()
    if not question:
        question = "我需要你确认一个选择后再继续。"
    choices = _clarification_choices(payload.get("choices"))
    slot_patch_schema = _clarification_slot_schema(payload.get("slot_patch_schema"), choices)
    raw_active_intent = str(payload.get("active_intent") or payload.get("intent") or "").strip()
    active_intent = canonical_action_for_intent(raw_active_intent, context=payload) or raw_active_intent
    continue_with = str(payload.get("continue_with") or payload.get("continueWith") or "").strip()
    if active_intent and (not continue_with or continue_with in {raw_active_intent, active_intent}):
        continue_with = display_title_for_action(active_intent)
    missing_slots = [
        str(item)
        for item in list(payload.get("missing_slots") or slot_patch_schema.keys())
        if str(item or "").strip()
    ]
    if active_intent == "export_result":
        slot_patch_schema = export_result_slot_patch_schema()
        missing_slots = export_result_missing_slots()
        question = export_result_question(question)
    pending_task = PendingTask.from_payload(
        {
            "source": "proactive_clarification",
            "pending_kind": str(payload.get("pending_kind") or ""),
            "awaiting_state": "awaiting_user",
            "active_intent": active_intent,
            "continue_with": continue_with,
            "filled_slots": make_json_safe(dict(payload.get("filled_slots") or {})),
            "missing_slots": missing_slots,
            "original_request": str(payload.get("original_request") or default_request or ""),
            "last_question_key": question,
            "last_question_params": {},
            "question": question,
            "choices": choices,
            "slot_patch_schema": slot_patch_schema,
            "source_requests": list(payload.get("source_requests") or []),
            "allowed_actions": list(payload.get("allowed_actions") or ["patch", "cancel", "replan"]),
            "ux_explanation": str(payload.get("ux_explanation") or question),
            "risk": make_json_safe(dict(payload.get("risk") or {})),
        }
    )
    return Observation(
        status="success",
        message=question,
        data={
            "meta_status": "awaiting_user",
            "pending_task": pending_task.to_dict(),
        },
    )


def _workspace_context(*, toolbox: Any, steps: list[Any] | None, session_id: str) -> dict[str, Any]:
    return make_json_safe(
        {
            "outputs": _artifact_outputs(toolbox),
            "risks": _step_risks(steps),
            "memory": _session_memory_summary(toolbox),
            "active_run": {
                "session_id": session_id,
                "step_count": len(list(steps or [])),
            },
        }
    )


def _clarification_choices(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for choice in list(value or []):
        if not isinstance(choice, dict):
            continue
        slot = str(choice.get("slot") or "").strip()
        if not slot or "value" not in choice:
            continue
        item = make_json_safe(dict(choice))
        item["slot"] = slot
        item["label"] = str(item.get("label") or item.get("value") or slot)
        result.append(item)
    return result


def _clarification_slot_schema(value: Any, choices: list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(value, dict) and value:
        return make_json_safe(dict(value))
    schema: dict[str, Any] = {}
    for choice in choices:
        slot = str(choice.get("slot") or "").strip()
        if not slot:
            continue
        schema.setdefault(
            slot,
            {
                "required": True,
                "type": "array" if isinstance(choice.get("value"), list) else "string",
            },
        )
    return make_json_safe(schema)


def _artifact_outputs(toolbox: Any) -> list[dict[str, Any]]:
    artifacts = getattr(toolbox, "artifacts", None)
    if artifacts is None or not hasattr(artifacts, "outputs"):
        return []
    try:
        return [dict(item) for item in list(artifacts.outputs(include_intermediate=True) or []) if isinstance(item, dict)]
    except Exception:
        return []


def _step_risks(steps: list[Any] | None) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for step in list(steps or []):
        observation = getattr(step, "observation", None)
        data = dict(getattr(observation, "data", None) or {})
        for key in ("preflight_warnings", "postflight_warnings"):
            for warning in list(data.get(key) or []):
                if not isinstance(warning, dict):
                    continue
                risk = warning.get("risk")
                risks.append(dict(risk if isinstance(risk, dict) and risk else warning))
    return risks


def _session_memory_summary(toolbox: Any) -> dict[str, Any]:
    workspace = getattr(toolbox, "workspace", None)
    path = getattr(workspace, "session_memory_path", None)
    if not path:
        return {"available": False}
    memory_path = Path(path)
    try:
        text = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    except OSError:
        text = ""
    return {
        "available": bool(text.strip()),
        "path": str(memory_path),
        "chars": len(text),
        "preview": text.strip()[:600],
    }
