"""Autonomy policy for hard/soft/silent runtime decisions.

This policy does not execute tools and does not override validation. It gives
the runtime a structured explanation of whether an issue should block, proceed
with an auditable assumption, or proceed silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.models import ActionPlan
from pineflow_agent.risks.models import GISRisk
from pineflow_agent.rules.validation import ValidationIssue

AutonomyLevel = Literal["hard", "soft", "silent"]


@dataclass(frozen=True)
class AutonomyDecision:
    level: AutonomyLevel
    reason: str
    assumption: str = ""
    audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return make_json_safe(
            {
                "level": self.level,
                "reason": self.reason,
                "assumption": self.assumption,
                "audit_required": self.audit_required,
            }
        )


class AutonomyPolicy:
    """Classify runtime validation issues without changing execution authority."""

    def decide_validation_issue(
        self,
        *,
        plan: ActionPlan,
        issue: ValidationIssue,
        risk: GISRisk | None = None,
    ) -> AutonomyDecision:
        code = str(issue.code or "")
        missing_slots = [str(item) for item in list(issue.params.get("missing_slots") or []) if str(item or "").strip()]
        action = str(plan.action or "")

        if code in {"unknown_layer", "unknown_field"}:
            return AutonomyDecision(
                level="hard",
                reason="Unknown layer or field cannot be repaired by assumption.",
            )

        if code == "missing_slot":
            return self._missing_slot_decision(action, missing_slots)

        if risk and (risk.blocking or risk.confirmation_required):
            return AutonomyDecision(
                level="hard",
                reason="Blocking or confirmation-required GIS risk must remain user-visible.",
            )

        if str(issue.stage or "") == "preflight" and str(issue.severity or "") == "warning":
            return AutonomyDecision(
                level="soft",
                reason="Non-blocking preflight warnings may proceed with an auditable assumption.",
                assumption=str(issue.message or ""),
            )

        return AutonomyDecision(
            level="hard",
            reason="Unclassified validation issue keeps the conservative hard boundary.",
        )

    def _missing_slot_decision(self, action: str, missing_slots: list[str]) -> AutonomyDecision:
        slots = set(missing_slots)
        if slots.intersection({"input_ref", "input_refs", "overlay_ref", "layer_ref", "raster_ref", "csv_ref"}):
            return AutonomyDecision(level="hard", reason="Missing data source cannot be guessed safely.")
        if slots.intersection({"field", "fields", "x_field", "y_field", "distance", "predicate", "expression", "value"}):
            return AutonomyDecision(level="hard", reason="Missing analytical parameter must be supplied or selected.")
        if "output_path" in slots and action == "export_result":
            return AutonomyDecision(level="hard", reason="Explicit export needs a user-visible destination path.")
        if "output_path" in slots:
            return AutonomyDecision(
                level="silent",
                reason="Intermediate processing outputs may use automatic naming.",
                assumption="Use runtime-generated output path for intermediate result.",
                audit_required=False,
            )
        if "target_crs" in slots:
            return AutonomyDecision(
                level="soft",
                reason="Target CRS may be derived from CRSRecommendationPolicy when confidence is high.",
                assumption="Use recommended projected CRS if runtime policy provides one.",
            )
        return AutonomyDecision(level="hard", reason="Missing slot has no safe default in AutonomyPolicy v1.")
