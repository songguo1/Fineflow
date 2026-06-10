"""Minimal goal contract for one agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pineflow_agent.core.json_safety import make_json_safe

GoalContractSource = Literal["inferred", "plan_approved", "user_supplied"]


@dataclass
class GoalContract:
    goal: str
    required_outputs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    quality_checks: list[str] = field(default_factory=list)
    source: GoalContractSource = "inferred"

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "goal": self.goal,
                "required_outputs": list(self.required_outputs),
                "constraints": list(self.constraints),
                "quality_checks": list(self.quality_checks),
                "source": self.source,
            }
        )


def infer_goal_contract(
    user_request: str,
    *,
    result: Any | None = None,
    source: GoalContractSource = "inferred",
) -> GoalContract:
    request = str(user_request or "").strip()
    required_outputs = _required_outputs(request)
    return GoalContract(
        goal=request or _result_message(result) or "Complete the GIS task.",
        required_outputs=required_outputs,
        constraints=_constraints_from_request(request),
        quality_checks=_quality_checks(required_outputs=required_outputs),
        source=source,
    )


def attach_goal_contract(
    result: Any,
    user_request: str,
    *,
    source: GoalContractSource = "inferred",
) -> Any:
    if result is None:
        return result
    existing = getattr(result, "goal_contract", None)
    if isinstance(existing, dict) and existing:
        return result
    try:
        result.goal_contract = infer_goal_contract(user_request, result=result, source=source).to_dict()
    except Exception:
        result.goal_contract = {}
    return result


def _result_message(result: Any | None) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        return str(result.get("final_message") or "")
    return str(getattr(result, "final_message", "") or "")


def _required_outputs(request: str) -> list[str]:
    required: list[str] = []
    if _contains_any(request, ["导出", "输出", "保存", "export", "save", "write"]):
        required.append("final_gis_output")
    if _contains_any(request, ["报告", "report", "总结", "summary"]):
        required.append("analysis_report")
    return required


def _constraints_from_request(request: str) -> list[str]:
    constraints: list[str] = []
    if _contains_any(request, ["距离", "缓冲", "buffer", "公里", "千米", "米", "km", "m"]):
        constraints.append("distance_or_buffer_analysis")
    if _contains_any(request, ["边界", "范围", "以内", "内", "within", "clip"]):
        constraints.append("boundary_or_extent_constraint")
    if _contains_any(request, ["筛选", "过滤", "where", "select", "extract"]):
        constraints.append("selection_or_filter_constraint")
    if _contains_any(request, ["crs", "坐标系", "投影", "重投影"]):
        constraints.append("crs_constraint")
    return constraints


def _quality_checks(*, required_outputs: list[str]) -> list[str]:
    checks = ["review_gis_risks", "record_reproducible_steps"]
    if "final_gis_output" in required_outputs:
        checks.extend(["final_output_recorded", "final_output_not_empty_if_applicable"])
    if "analysis_report" in required_outputs:
        checks.append("analysis_report_recorded")
    return checks


def _contains_any(text: str, needles: list[str]) -> bool:
    lowered = str(text or "").lower()
    return any(needle.lower() in lowered for needle in needles)
