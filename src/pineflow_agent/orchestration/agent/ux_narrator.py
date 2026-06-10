"""User-facing narration helpers for GIS pauses and observations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pineflow_agent.core.models import ActionPlan, Observation
from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action


class UXNarrator:
    """Creates human-readable text without changing GIS decisions."""

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm

    def explain_validation_pause(
        self,
        *,
        user_request: str,
        plan: ActionPlan,
        issue: Any,
        risk: dict[str, Any] | None,
        awaiting_state: str,
    ) -> str:
        fallback = _fallback_pause_explanation(
            plan=plan,
            issue=issue,
            risk=risk or {},
            awaiting_state=awaiting_state,
        )
        prompt = {
            "task": "Explain a GIS validation pause to an end user in one concise Chinese sentence.",
            "rules": [
                "Do not change parameters or recommend a different operation.",
                "Do not expose raw JSON, Python, QGIS exception text, or internal field names unless necessary.",
                "If confirmation is needed, end with a short confirmation question.",
            ],
            "user_request": user_request,
            "tool": plan.action,
            "tool_input": plan.action_input,
            "issue": issue.to_dict() if hasattr(issue, "to_dict") else {},
            "risk": risk or {},
            "awaiting_state": awaiting_state,
            "fallback": fallback,
        }
        return self._llm_sentence(prompt, fallback=fallback)

    def summarize_observation(
        self,
        *,
        plan: ActionPlan,
        observation: Observation,
        state_tree: dict[str, Any],
    ) -> str:
        fallback = _fallback_observation_summary(plan=plan, observation=observation)
        prompt = {
            "task": "Summarize one completed GIS processing step for an end user in one concise Chinese sentence.",
            "rules": [
                "Use only facts from the observation and state tree.",
                "Do not invent counts, CRS, paths, or interpretations.",
                "Avoid raw JSON and developer wording.",
            ],
            "tool": plan.action,
            "tool_input": plan.action_input,
            "observation": observation.to_dict(),
            "state_tree": state_tree,
            "fallback": fallback,
        }
        return self._llm_sentence(prompt, fallback=fallback)

    def narrate_key_event(self, event: str, payload: dict[str, Any]) -> str:
        """Generate display copy for a structured runtime event.

        The payload is the source of truth. The LLM may only turn those facts into
        user-facing copy; it must not change any parameter, decision, or state.
        """

        event_name = str(event or "").strip()
        if event_name == "before_export":
            fallback = _fallback_before_export(payload)
            task = "Explain that PineFlow is about to export a GIS result in one concise Chinese sentence."
        elif event_name == "empty_result":
            fallback = _fallback_empty_result(payload)
            task = "Explain that a GIS step succeeded but produced an empty result in one concise Chinese sentence."
        elif event_name == "repair_success":
            fallback = _fallback_repair_success(payload)
            task = "Explain that a GIS repair completed and the workflow can continue in one concise Chinese sentence."
        else:
            fallback = str(payload.get("message") or "").strip()
            task = "Write one concise Chinese sentence for a GIS runtime event."
        prompt = {
            "task": task,
            "rules": [
                "Use only the facts in payload.",
                "Do not invent feature counts, CRS, paths, layer names, or decisions.",
                "Do not expose raw JSON, Python terms, or internal implementation details.",
                "Return plain text only.",
            ],
            "event": event_name,
            "payload": payload,
            "fallback": fallback,
        }
        return self._llm_sentence(prompt, fallback=fallback)

    def _llm_sentence(self, payload: dict[str, Any], *, fallback: str) -> str:
        if self.llm is None:
            return fallback
        complete = getattr(self.llm, "complete_text", None)
        if complete is None:
            if hasattr(self.llm, "tool_call"):
                return fallback
            complete = getattr(self.llm, "complete", None)
        if complete is None:
            return fallback
        try:
            raw = complete(
                system_prompt="You write short, factual, user-facing GIS UI copy. Return plain text only.",
                user_prompt=json.dumps(payload, ensure_ascii=False),
            )
        except Exception:
            return fallback
        text = _clean_sentence(raw)
        return text or fallback


def _fallback_pause_explanation(
    *,
    plan: ActionPlan,
    issue: Any,
    risk: dict[str, Any],
    awaiting_state: str,
) -> str:
    message = str(risk.get("message") or getattr(issue, "message", "") or "").strip()
    action = _friendly_action(plan.action)
    if awaiting_state == "awaiting_confirmation":
        if message:
            return f"我发现{message}。为了继续执行{action}，需要你确认是否按建议处理。"
        return f"继续执行{action}前需要你确认一个 GIS 风险。"
    if message:
        return f"我发现{message}。请补充或选择合适的信息后继续。"
    return f"继续执行{action}前还需要补充一些信息。"


def _fallback_observation_summary(*, plan: ActionPlan, observation: Observation) -> str:
    layer = dict((observation.data or {}).get("layer") or {})
    metadata = dict(layer.get("metadata") or {})
    feature_count = metadata.get("feature_count")
    geometry_type = str(metadata.get("geometry_type") or "").strip()
    name = str(layer.get("name") or observation.output_layer_id or "").strip()
    action = _friendly_action(plan.action)
    if observation.is_success:
        if plan.action == "export_result" and observation.output_path:
            return f"结果已导出为 {Path(observation.output_path).name}。"
        if feature_count == 0:
            return f"{action}已完成，但输出结果为空，需要结合输入范围、筛选条件和 CRS 继续检查。"
        if plan.action == "fix_geometries":
            target = str(plan.action_input.get("input_ref") or name or "输入图层").strip()
            return f"几何修复已完成，已生成可用于后续分析的 {target} 修复结果。"
        parts = [f"{action}已完成"]
        if name:
            parts.append(f"生成了 {name}")
        if feature_count is not None:
            parts.append(f"{feature_count} 个要素")
        if geometry_type:
            parts.append(geometry_type)
        return "，".join(parts) + "。"
    return f"{action}没有完成：{observation.message}"


def _fallback_before_export(payload: dict[str, Any]) -> str:
    export = dict(payload.get("export") or payload)
    layer_name = str(export.get("layer_name") or export.get("layer_ref") or "当前图层")
    output_name = str(export.get("output_name") or export.get("output_path") or "指定位置")
    feature_count = export.get("feature_count")
    count_text = f"{feature_count} 个要素" if feature_count is not None else "已生成的要素"
    return f"准备导出 {layer_name}（{count_text}）到 {output_name}。"


def _fallback_empty_result(payload: dict[str, Any]) -> str:
    warning = dict(payload.get("warning") or payload)
    risk = dict(warning.get("risk") or payload.get("risk") or {})
    diagnosis = dict(risk.get("diagnosis") or warning.get("diagnosis") or payload.get("diagnosis") or {})
    causes = list(diagnosis.get("possible_causes") or [])
    actions = _diagnosis_action_texts(diagnosis)
    if causes:
        return "这一步执行成功但结果为空；可能原因：" + "；".join(str(item) for item in causes[:2]) + "。"
    if actions:
        return "这一步执行成功但结果为空；建议：" + "；".join(str(item) for item in actions[:2]) + "。"
    return str(warning.get("message") or "这一步执行成功但结果为空，需要检查输入范围、筛选条件和 CRS。")


def _fallback_repair_success(payload: dict[str, Any]) -> str:
    audit = dict(payload.get("repair_audit") or payload)
    input_name = str(dict(audit.get("input") or {}).get("name") or "输入图层")
    output_name = str(dict(audit.get("output") or {}).get("name") or "修复结果")
    before = audit.get("feature_count_before")
    after = audit.get("feature_count_after")
    prefix = "已按确认修复" if str(audit.get("decision") or "") == "user_confirmed_repair" else "已修复"
    if before is not None and after is not None:
        return f"{prefix} {input_name}，生成 {output_name}；要素数从 {before} 变为 {after}，后续分析将继续使用修复后的图层。"
    return f"{prefix} {input_name}，生成 {output_name}，后续分析将继续使用修复后的图层。"


def _clean_sentence(raw: Any) -> str:
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    if text.startswith("{") or text.startswith("["):
        return ""
    lowered = text.lower()
    if "action_input" in lowered or "tool_call" in lowered or "```" in text:
        return ""
    return text.replace("\n", " ").strip()[:300]


def _friendly_action(action: str) -> str:
    key = str(action or "").strip()
    return display_title_for_action(key) or "当前操作"


def _diagnosis_action_texts(diagnosis: dict[str, Any]) -> list[str]:
    labels = [
        str(item.get("label") or "").strip()
        for item in list(diagnosis.get("suggested_action_options") or [])
        if isinstance(item, dict)
    ]
    if any(labels):
        return [label for label in labels if label]
    return [
        str(item).strip()
        for item in list(diagnosis.get("suggested_actions") or diagnosis.get("suggested_next_actions") or [])
        if str(item or "").strip()
    ]
