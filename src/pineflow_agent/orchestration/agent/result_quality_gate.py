"""Minimal final-result quality gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import AgentResult, ReActStep


@dataclass(frozen=True)
class QualityGateFinding:
    code: str
    severity: str
    message: str
    blocking: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    affected_artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "code": self.code,
                "severity": self.severity,
                "message": self.message,
                "blocking": self.blocking,
                "detail": dict(self.detail or {}),
                "affected_artifacts": list(self.affected_artifacts or []),
            }
        )


def evaluate_result_quality(result: AgentResult) -> list[dict[str, Any]]:
    goal_contract = dict(result.goal_contract or {})
    required_outputs = {str(item) for item in list(goal_contract.get("required_outputs") or []) if str(item)}
    payload = result.to_dict()
    outputs = [dict(item) for item in list(payload.get("outputs") or []) if isinstance(item, dict)]
    findings: list[QualityGateFinding] = []

    final_outputs = [output for output in outputs if _is_final_output(output)]
    if "final_gis_output" in required_outputs and not final_outputs:
        findings.append(
            QualityGateFinding(
                code="missing_final_output",
                severity="error",
                message="GoalContract requires a final GIS output, but no exported final output was recorded.",
                blocking=True,
                detail={"required_output": "final_gis_output"},
                affected_artifacts=[],
            )
        )

    for output in final_outputs or outputs:
        feature_count = output.get("feature_count")
        if feature_count == 0:
            findings.append(
                QualityGateFinding(
                    code="empty_final_output",
                    severity="warning",
                    message=f"Final output {output.get('name') or output.get('layer_id') or 'output'} has 0 features.",
                    blocking="final_output_not_empty_if_applicable" in set(goal_contract.get("quality_checks") or []),
                    detail={"output": output},
                    affected_artifacts=[_artifact_ref(output)],
                )
            )

    for warning in _warnings(result.steps):
        risk = dict(warning.get("risk") or {})
        severity = str(risk.get("severity") or warning.get("severity") or "warning")
        category = str(risk.get("category") or warning.get("category") or "")
        affects_result_trust = bool(risk.get("affects_result_trust", warning.get("affects_result_trust", False)))
        if bool(risk.get("blocking")) or severity == "error" or _should_promote_warning_to_quality(category, risk, warning, affects_result_trust):
            findings.append(
                QualityGateFinding(
                    code=str(risk.get("code") or warning.get("code") or "unresolved_risk"),
                    severity=severity,
                    message=str(risk.get("message") or warning.get("message") or "Unresolved GIS risk."),
                    blocking=bool(risk.get("blocking")),
                    detail={
                        "risk": risk or warning,
                        "diagnosis": dict(risk.get("diagnosis") or warning.get("diagnosis") or {}),
                        "source": str(warning.get("source") or ""),
                    },
                    affected_artifacts=_affected_artifacts_from_warning(warning),
                )
            )

    return [finding.to_dict() for finding in _dedupe_findings(findings)]


def _is_final_output(output: dict[str, Any]) -> bool:
    role = str(output.get("role") or "")
    algorithm_id = str(output.get("algorithm_id") or "")
    return role == "final" or algorithm_id == "export_result"


def has_blocking_findings(findings: list[dict[str, Any]]) -> bool:
    return any(bool(item.get("blocking")) for item in list(findings or []) if isinstance(item, dict))


def quality_gate_already_blocked(steps: list[ReActStep]) -> bool:
    for step in list(steps or []):
        data = dict(step.observation.data or {})
        if data.get("quality_gate_blocked"):
            return True
    return False


def blocking_quality_message(findings: list[dict[str, Any]]) -> str:
    blocking = [dict(item) for item in list(findings or []) if isinstance(item, dict) and item.get("blocking")]
    if not blocking:
        return ""
    joined = "; ".join(str(item.get("message") or item.get("code") or "quality finding") for item in blocking[:3])
    return f"Final answer blocked by result quality gate: {joined}"


def _warnings(steps: list[ReActStep]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for step in list(steps or []):
        data = dict(step.observation.data or {})
        for key in ("preflight_warnings", "postflight_warnings"):
            items.extend(dict(item) for item in list(data.get(key) or []) if isinstance(item, dict))
    return items


def _artifact_ref(output: dict[str, Any]) -> dict[str, Any]:
    return make_json_safe(
        {
            "artifact_id": str(output.get("artifact_id") or ""),
            "layer_id": str(output.get("layer_id") or ""),
            "name": str(output.get("name") or output.get("layer_id") or ""),
            "path": str(output.get("path") or output.get("output_path") or output.get("source") or ""),
            "role": str(output.get("role") or ""),
            "kind": str(output.get("kind") or ""),
            "source_action": str(output.get("source_action") or ""),
            "source_step": output.get("source_step"),
            "feature_count": output.get("feature_count"),
            "crs": str(output.get("crs") or ""),
            "display_summary": str(output.get("display_summary") or ""),
        }
    )


def _affected_artifacts_from_warning(warning: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = warning.get("affected_artifacts")
    if isinstance(artifacts, list):
        return [make_json_safe(dict(item)) for item in artifacts if isinstance(item, dict)]
    output_artifact = warning.get("output_artifact")
    if isinstance(output_artifact, dict):
        return [_artifact_ref(output_artifact)]
    artifact = warning.get("artifact")
    if isinstance(artifact, dict):
        return [_artifact_ref(artifact)]
    layer = warning.get("layer")
    if isinstance(layer, dict):
        return [_artifact_ref(layer)]
    return []


def _should_promote_warning_to_quality(
    category: str,
    risk: dict[str, Any],
    warning: dict[str, Any],
    affects_result_trust: bool,
) -> bool:
    if not affects_result_trust:
        return False
    code = str(risk.get("code") or warning.get("code") or "")
    if category == "raster_risk":
        return True
    if code == "contour_empty_output":
        return True
    return False


def _dedupe_findings(findings: list[QualityGateFinding]) -> list[QualityGateFinding]:
    seen: set[tuple[str, str]] = set()
    result: list[QualityGateFinding] = []
    for finding in findings:
        key = (finding.code, finding.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result
