"""Unified validation gateway before tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pineflow_agent.core.models import ActionPlan
from pineflow_agent.core.state_tree import GISStateTree
from pineflow_agent.rules import preflight as _preflight_rules  # noqa: F401 - register built-in preflight rules
from pineflow_agent.rules.rule_registry import RuleRegistry
from pineflow_agent.rules.validation import ValidationIssue
from pineflow_agent.tools.registry.tool_registry import ToolRegistry


ValidationPhase = Literal["semantic", "preflight"]


@dataclass(frozen=True)
class RuleGatewayResult:
    phase: ValidationPhase
    issues: list[ValidationIssue]

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


@dataclass
class RulesGateway:
    """Runs schema, semantic, and GIS preflight validation through one entry point."""

    registry: RuleRegistry = field(default_factory=RuleRegistry.default)

    def semantic_issues(
        self,
        plan: ActionPlan,
        registry: ToolRegistry,
        *,
        collect_all: bool = False,
    ) -> list[ValidationIssue]:
        return self.registry.issues("semantic", plan, registry=registry, collect_all=collect_all)

    def preflight_issues(
        self,
        plan: ActionPlan,
        state: GISStateTree,
        *,
        collect_all: bool = False,
    ) -> list[ValidationIssue]:
        return self.registry.issues("preflight", plan, state=state, collect_all=collect_all)

    def validate(
        self,
        plan: ActionPlan,
        *,
        state: GISStateTree,
        registry: ToolRegistry,
        collect_all: bool = False,
    ) -> RuleGatewayResult:
        semantic = self.semantic_issues(plan, registry, collect_all=collect_all)
        if semantic:
            return RuleGatewayResult("semantic", semantic)
        preflight = self.preflight_issues(plan, state, collect_all=collect_all)
        if preflight:
            return RuleGatewayResult("preflight", preflight)
        return RuleGatewayResult("preflight", [])
