"""Decision policy for GIS risks."""

from __future__ import annotations

from pineflow_agent.risks.models import GISRisk, RiskDecision


class RiskPolicy:
    """Small v1 policy layer that preserves current behavior while exposing intent."""

    def evaluate(self, risks: list[GISRisk] | tuple[GISRisk, ...]) -> RiskDecision:
        ordered = tuple(risks or ())
        if not ordered:
            return RiskDecision("proceed")
        primary = ordered[0]
        if primary.suggested_choices:
            return RiskDecision("ask_disambiguation", primary, ordered)
        if primary.confirmation_required:
            return RiskDecision("ask_confirmation", primary, ordered)
        if primary.auto_repair_available and primary.repair_action and not primary.confirmation_required:
            return RiskDecision("auto_repair", primary, ordered)
        if primary.blocking or primary.severity == "error":
            return RiskDecision("ask_user", primary, ordered)
        return RiskDecision("warn", primary, ordered)
