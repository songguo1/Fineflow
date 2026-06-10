"""Structured GIS risk contracts used across validation and runtime stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pineflow_agent.core.json_safety import make_json_safe

RiskSeverity = Literal["info", "warning", "error"]
RiskDecisionKind = Literal[
    "proceed",
    "warn",
    "ask_user",
    "ask_confirmation",
    "ask_disambiguation",
    "auto_repair",
    "fail",
]


@dataclass
class GISRisk:
    code: str
    category: str
    severity: RiskSeverity
    stage: str
    message: str
    technical_detail: str = ""
    tool_name: str = ""
    layer_refs: list[str] = field(default_factory=list)
    confirmation_required: bool = False
    blocking: bool = False
    auto_repair_available: bool = False
    repair_action: dict[str, Any] | None = None
    suggested_choices: list[dict[str, Any]] = field(default_factory=list)
    diagnosis: dict[str, Any] = field(default_factory=dict)
    affects_result_trust: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "stage": self.stage,
            "message": self.message,
            "technical_detail": self.technical_detail,
            "tool_name": self.tool_name,
            "layer_refs": make_json_safe(list(self.layer_refs)),
            "confirmation_required": self.confirmation_required,
            "blocking": self.blocking,
            "auto_repair_available": self.auto_repair_available,
            "repair_action": make_json_safe(self.repair_action or {}),
            "suggested_choices": make_json_safe(list(self.suggested_choices)),
            "diagnosis": make_json_safe(dict(self.diagnosis or {})),
            "affects_result_trust": self.affects_result_trust,
        }


@dataclass(frozen=True)
class RiskDecision:
    kind: RiskDecisionKind
    primary_risk: GISRisk | None = None
    risks: tuple[GISRisk, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "primary_risk": self.primary_risk.to_dict() if self.primary_risk else {},
            "risks": [risk.to_dict() for risk in self.risks],
        }
