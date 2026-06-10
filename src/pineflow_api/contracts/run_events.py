"""Run event contract helpers.

The legacy event shape is intentionally preserved.  These helpers add the
stable run/event fields that UI projections can consume without parsing logs.
"""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.orchestration.event_stream import enrich_event_contract
from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action
from pineflow_api.contracts.transcript_projection import ensure_transcript_item_identity


DEBUG_EVENT_TYPES = {
    "run.thought",
    "run.review",
    "tool.command",
    "tool.log",
    "tool.error",
    "tool.selected",
    "toolkit.selected",
}

DEBUG_KEYS = {
    "command",
    "stdout",
    "stderr",
    "stream",
    "raw",
    "traceback",
    "timing",
}

FACT_KEYS = {
    "action",
    "action_input",
    "algorithm_id",
    "observation",
    "warning",
    "risk",
    "risk_decision",
    "pending_task",
    "repair",
    "repair_session",
    "repair_audit",
    "repair_step_index",
    "repair_goal",
    "result",
    "step_index",
    "step_total",
    "attempt_no",
    "source",
    "diagnosis",
    "export",
    "artifact",
    "output_artifact",
    "role",
    "source_action",
    "clarification_decision",
    "output_layer_id",
    "output_path",
    "issues",
    "risks",
}


def normalize_run_event(
    event: dict[str, Any],
    *,
    session_id: str = "",
    run_id: str = "",
    seq: int = 0,
    created_at: str = "",
) -> dict[str, Any]:
    """Return a JSON-safe event with Event Contract v1 fields attached."""
    payload = enrich_event_contract(dict(event or {}))
    payload["session_id"] = str(session_id or payload.get("session_id") or "")
    payload["run_id"] = str(run_id or payload.get("run_id") or "")
    if seq:
        payload["seq"] = int(seq)
    if created_at:
        payload["created_at"] = str(created_at)
    if not str(payload.get("display_title") or "").strip():
        payload["display_title"] = _display_title(payload)
    if not str(payload.get("display_summary") or "").strip():
        payload["display_summary"] = _display_summary(payload)
    if not isinstance(payload.get("payload"), dict):
        payload["payload"] = _fact_payload(payload)
    if not isinstance(payload.get("debug_payload"), dict):
        payload["debug_payload"] = _debug_payload(payload)
    if isinstance(payload.get("transcript_item"), dict):
        payload["transcript_item"] = _transcript_item_with_event_meta(payload["transcript_item"], payload)
    return make_json_safe(payload)


def _display_title(event: dict[str, Any]) -> str:
    for key in ("action", "algorithm_id"):
        action = str(event.get(key) or "").strip()
        if action:
            return display_title_for_action(action)
    event_type = str(event.get("event_type") or "").strip()
    event_name = str(event.get("event") or "").strip()
    return {
        "run.completed": "任务完成",
        "run.failed": "任务失败",
        "run.cancelled": "任务已取消",
        "run.paused": "任务已暂停",
        "risk.warning": "数据质量提示",
        "warning.emitted": "数据质量提示",
        "result.empty": "空结果诊断",
        "tool.started": "开始执行",
        "tool.completed": "执行完成",
        "tool.failed": "执行失败",
        "artifact.created": "生成结果",
        "repair.confirmation_requested": "等待确认",
        "repair.started": "准备修复",
        "repair.completed": "修复完成",
        "repair.failed": "修复失败",
        "export.before": "准备导出",
        "user_input.requested": "需要输入",
        "workflow.step_started": "执行步骤",
        "workflow.step_completed": "步骤完成",
    }.get(event_type, event_name or "运行事件")


def _display_summary(event: dict[str, Any]) -> str:
    message = str(event.get("message") or "").strip()
    if message:
        return message
    result = event.get("result")
    if isinstance(result, dict):
        text = str(result.get("final_message") or result.get("next_question") or "").strip()
        if text:
            return text
    return ""


def _fact_payload(event: dict[str, Any]) -> dict[str, Any]:
    return make_json_safe({key: event[key] for key in FACT_KEYS if key in event})


def _debug_payload(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "").strip()
    values = {key: event[key] for key in DEBUG_KEYS if key in event}
    if event_type in DEBUG_EVENT_TYPES:
        for key in ("message", "event", "event_type"):
            if key in event:
                values[key] = event[key]
    return make_json_safe(values)


def _transcript_item_with_event_meta(item: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    for key in ("session_id", "run_id", "created_at"):
        value = str(event.get(key) or "").strip()
        if value:
            enriched[key] = value
    seq = int(event.get("seq") or 0)
    if seq > 0:
        enriched["seq"] = seq
    return ensure_transcript_item_identity(enriched)
