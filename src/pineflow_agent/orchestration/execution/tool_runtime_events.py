"""Structured Tool Runtime Event v2 emission helpers."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import ActionPlan, Observation
from pineflow_agent.orchestration.event_stream import EventHandler, emit_event
from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action


class ToolRuntimeEventEmitter:
    """Emit structured tool runtime facts while preserving legacy event names."""

    def __init__(
        self,
        on_event: EventHandler | None,
        *,
        session_id: str,
        step_index: int,
        step_total: int = 0,
        attempt_no: int = 0,
    ) -> None:
        self.on_event = on_event
        self.session_id = session_id
        self.step_index = int(step_index or 0)
        self.step_total = int(step_total or 0)
        self.attempt_no = int(attempt_no or 0)

    def tool_started(self, plan: ActionPlan, *, message: str, command: str = "") -> None:
        emit_event(
            self.on_event,
            "tool",
            message,
            event_type="tool.started",
            display_kind="progress",
            display_title=display_title_for_action(plan.action),
            display_summary=message,
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=plan.action,
            action_input=dict(plan.action_input or {}),
            command=str(command or ""),
            attempt_no=self.attempt_no,
        )

    def before_export(self, plan: ActionPlan, *, message: str, export: dict[str, Any]) -> None:
        emit_event(
            self.on_event,
            "before_export",
            message,
            event_type="export.before",
            display_kind="progress",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=plan.action,
            action_input=dict(plan.action_input or {}),
            export=make_json_safe(dict(export or {})),
            attempt_no=self.attempt_no,
        )

    def warning(self, plan: ActionPlan, warning: dict[str, Any], *, source: str, message: str = "") -> None:
        risk = warning.get("risk") if isinstance(warning.get("risk"), dict) else {}
        emit_event(
            self.on_event,
            "warning",
            str(message or warning.get("message") or warning.get("code") or "Runtime warning."),
            event_type="warning.emitted",
            display_kind="warning",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=plan.action,
            action_input=dict(plan.action_input or {}),
            warning=make_json_safe(dict(warning or {})),
            risk=make_json_safe(dict(risk or {})),
            source=source,
            attempt_no=self.attempt_no,
        )

    def empty_result(self, plan: ActionPlan, *, warning: dict[str, Any], message: str, diagnosis: dict[str, Any]) -> None:
        risk = warning.get("risk") if isinstance(warning.get("risk"), dict) else {}
        emit_event(
            self.on_event,
            "empty_result",
            message,
            event_type="result.empty",
            display_kind="warning",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=plan.action,
            action_input=dict(plan.action_input or {}),
            warning=make_json_safe(dict(warning or {})),
            risk=make_json_safe(dict(risk or {})),
            diagnosis=make_json_safe(dict(diagnosis or {})),
            source="postflight",
            attempt_no=self.attempt_no,
        )

    def tool_finished(
        self,
        plan: ActionPlan,
        observation: Observation,
        *,
        state_tree: dict[str, Any],
        output_artifact: dict[str, Any] | None = None,
        timing: dict[str, Any] | None = None,
    ) -> None:
        event_type = "tool.completed" if observation.is_success else "tool.failed"
        emit_event(
            self.on_event,
            "observation",
            observation.message,
            event_type=event_type,
            display_kind="workflow_step",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=plan.action,
            action_input=dict(plan.action_input or {}),
            observation=observation.to_dict(),
            output_layer_id=observation.output_layer_id,
            output_path=observation.output_path,
            output_artifact=make_json_safe(dict(output_artifact or {})),
            state_tree=state_tree,
            timing=make_json_safe(dict(timing or {})),
            attempt_no=self.attempt_no,
        )

    def artifact_created(
        self,
        plan: ActionPlan,
        observation: Observation,
        *,
        artifact: dict[str, Any] | None = None,
    ) -> None:
        artifact = dict(artifact or _observation_artifact(observation) or _observation_layer(observation))
        if not artifact or not observation.is_success:
            return
        role = str(artifact.get("role") or ("final" if str(artifact.get("algorithm_id") or "") == "export_result" else "intermediate"))
        emit_event(
            self.on_event,
            "artifact",
            _artifact_event_summary(artifact, role=role),
            event_type="artifact.created",
            display_kind="result",
            display_title=str(artifact.get("display_title") or "输出结果"),
            display_summary=_artifact_event_summary(artifact, role=role),
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=plan.action,
            source_action=plan.action,
            artifact=make_json_safe(dict(artifact)),
            role=role,
            attempt_no=self.attempt_no,
        )

    def repair_started(
        self,
        *,
        action: str,
        message: str,
        repair_session: dict[str, Any] | None = None,
        repair_step_index: int = 0,
        repair_goal: str = "",
        issues: list[dict[str, Any]] | None = None,
        risks: list[dict[str, Any]] | None = None,
        risk: dict[str, Any] | None = None,
        risk_decision: dict[str, Any] | None = None,
        repair: dict[str, Any] | None = None,
    ) -> None:
        emit_event(
            self.on_event,
            "repair",
            message,
            event_type="repair.started",
            display_kind="progress",
            display_title="准备修复",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=action,
            repair_session=make_json_safe(dict(repair_session or {})),
            repair_step_index=int(repair_step_index or 0),
            repair_goal=str(repair_goal or ""),
            issues=make_json_safe(list(issues or [])),
            risks=make_json_safe(list(risks or [])),
            risk=make_json_safe(dict(risk or {})),
            risk_decision=make_json_safe(dict(risk_decision or {})),
            repair=make_json_safe(dict(repair or {})),
            attempt_no=self.attempt_no,
        )

    def repair_completed(
        self,
        *,
        action: str,
        message: str,
        repair_session: dict[str, Any] | None = None,
        repair_audit: dict[str, Any] | None = None,
        repair_step_index: int = 0,
        repair_goal: str = "",
    ) -> None:
        emit_event(
            self.on_event,
            "repair_success",
            message,
            event_type="repair.completed",
            display_kind="progress",
            display_title="修复完成",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=action,
            repair_session=make_json_safe(dict(repair_session or {})),
            repair_audit=make_json_safe(dict(repair_audit or {})),
            repair_step_index=int(repair_step_index or 0),
            repair_goal=str(repair_goal or ""),
            attempt_no=self.attempt_no,
        )

    def repair_failed(
        self,
        *,
        action: str = "",
        message: str,
        repair_session: dict[str, Any] | None = None,
        repair_step_index: int = 0,
        repair_goal: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        emit_event(
            self.on_event,
            "failed",
            message,
            event_type="repair.failed",
            display_kind="progress",
            display_title="修复失败",
            session_id=self.session_id,
            step_index=self.step_index,
            step_total=self.step_total,
            action=action,
            repair_session=make_json_safe(dict(repair_session or {})),
            repair_step_index=int(repair_step_index or 0),
            repair_goal=str(repair_goal or ""),
            result=make_json_safe(dict(result or {})),
            attempt_no=self.attempt_no,
        )


def _observation_layer(observation: Observation) -> dict[str, Any]:
    data = dict(observation.data or {})
    layer = data.get("layer")
    return dict(layer) if isinstance(layer, dict) else {}


def _observation_artifact(observation: Observation) -> dict[str, Any]:
    data = dict(observation.data or {})
    artifact = data.get("output_artifact") or data.get("artifact")
    return dict(artifact) if isinstance(artifact, dict) else {}


def _artifact_event_summary(artifact: dict[str, Any], *, role: str) -> str:
    display_summary = str(artifact.get("display_summary") or "").strip()
    if display_summary:
        return display_summary
    name = str(artifact.get("name") or artifact.get("layer_id") or artifact.get("artifact_id") or "结果").strip()
    role_label = {
        "input": "输入数据",
        "intermediate": "中间结果",
        "final": "最终结果",
        "report": "报告",
    }.get(str(role or "").strip().lower(), "结果")
    return f"已记录{role_label} {name}。"
