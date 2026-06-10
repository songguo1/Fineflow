"""Registered validation rules used by the unified rules gateway."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pineflow_agent.core.field_metadata import field_names
from pineflow_agent.core.models import ActionPlan
from pineflow_agent.core.state_tree import GISStateTree, LayerRecord
from pineflow_agent.rules.validation import RepairProposal, ValidationIssue

if TYPE_CHECKING:
    from pineflow_agent.tools.registry.tool_registry import ToolRegistry

RuleStage = Literal["semantic", "preflight", "resume"]
RuleCheck = Callable[["RuleEvaluationContext"], list[ValidationIssue]]


@dataclass(frozen=True)
class RuleEvaluationContext:
    plan: ActionPlan
    action_input: dict[str, Any]
    state: GISStateTree | None = None
    registry: "ToolRegistry | None" = None
    observation: Any = None
    previous_step: Any = None


@dataclass(frozen=True)
class RuleDefinition:
    name: str
    stage: RuleStage
    check: RuleCheck
    actions: tuple[str, ...] = ()

    def applies_to(self, plan: ActionPlan) -> bool:
        return not self.actions or plan.action in self.actions


@dataclass(frozen=True)
class RuleRegistry:
    rules: tuple[RuleDefinition, ...]

    @classmethod
    def register(cls, *, name: str, stage: RuleStage, actions: tuple[str, ...] = ()):
        """Decorator to register a rule function. Usage:

            @RuleRegistry.register(name="my_rule", stage="semantic", actions=("buffer_layer",))
            def my_rule(ctx: RuleEvaluationContext) -> list[ValidationIssue]:
                ...
        """
        def decorator(fn: RuleCheck) -> RuleCheck:
            cls.add_rule(RuleDefinition(name=name, stage=stage, check=fn, actions=actions))
            return fn
        return decorator

    @classmethod
    def add_rule(cls, definition: RuleDefinition) -> None:
        if not hasattr(cls, "_decorated_rules"):
            cls._decorated_rules = []
        cls._decorated_rules.append(definition)

    @classmethod
    def default(cls) -> "RuleRegistry":
        builtin = (
            RuleDefinition("schema_required_slots", "semantic", _schema_required_issues),
            RuleDefinition("layer_kind_requirements", "preflight", _layer_kind_requirement_issues),
            RuleDefinition("geometry_requirements", "preflight", _geometry_requirement_issues),
            RuleDefinition("field_requirements", "preflight", _field_requirement_issues),
        )
        decorated = getattr(cls, "_decorated_rules", [])
        return cls(rules=builtin + tuple(decorated))

    def issues(
        self,
        stage: RuleStage,
        plan: ActionPlan,
        *,
        state: GISStateTree | None = None,
        registry: "ToolRegistry | None" = None,
        observation: Any = None,
        previous_step: Any = None,
        collect_all: bool = False,
    ) -> list[ValidationIssue]:
        context = RuleEvaluationContext(
            plan=plan,
            action_input=_normalized_action_input(plan),
            state=state,
            registry=registry,
            observation=observation,
            previous_step=previous_step,
        )
        all_issues: list[ValidationIssue] = []
        for rule in self.rules:
            if rule.stage != stage or not rule.applies_to(plan):
                continue
            issues = rule.check(context)
            if issues:
                if not collect_all:
                    return issues
                all_issues.extend(issues)
        return all_issues


def _schema_required_issues(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.registry is None:
        return []
    plan = context.plan
    tool = context.registry.registered_tools().get(plan.action)
    if tool is None:
        message = f"Tool {plan.action or '<empty>'} is not registered."
        return [_ask_user_issue("unknown_tool", "semantic", message, {"action": plan.action})]

    parameters = ((tool.json_schema or {}).get("function") or {}).get("parameters") or {}
    required = [str(item) for item in list(parameters.get("required") or []) if str(item)]
    missing = [slot for slot in required if _is_missing(context.action_input.get(slot))]
    if not missing:
        return []
    message_key = _missing_slot_message_key(tool, missing)
    params = {"action": plan.action, "missing_slots": missing}
    return [
        ValidationIssue(
            code="missing_slot",
            stage="semantic",
            severity="error",
            message_key=message_key,
            params=params,
            repair=RepairProposal(
                kind="ask_user",
                message_key=message_key,
                params=params,
            ),
        )
    ]


def _missing_slot_message_key(tool: Any, missing_slots: list[str]) -> str:
    contract = dict(getattr(tool, "contract", None) or {})
    messages = dict(contract.get("missing_slot_messages") or {})
    for slot in list(missing_slots or []):
        key = str(messages.get(str(slot)) or "").strip()
        if key:
            return key
    default_key = str(messages.get("*") or "").strip()
    if default_key:
        return default_key
    return "semantic.missing_slots"


def _layer_kind_requirement_issues(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.state is None:
        return []
    from pineflow_agent.tools.contracts.tool_definitions import tool_definition_for_action

    definition = tool_definition_for_action(context.plan.action)
    if definition is None:
        return []

    for slot, expected_kind in definition.layer_requirements:
        value = context.action_input.get(slot)
        if slot in {"input_refs", "raster_refs"}:
            for item in list(value or []):
                issue = _layer_kind_issue(context.state, str(item or ""), expected_kind)
                if issue:
                    return [issue]
            continue
        issue = _layer_kind_issue(context.state, str(value or ""), expected_kind)
        if issue:
            return [issue]
    return []


def _geometry_requirement_issues(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.state is None:
        return []
    from pineflow_agent.tools.contracts.tool_definitions import tool_definition_for_action

    definition = tool_definition_for_action(context.plan.action)
    if definition is None:
        return []

    for slot, expected in definition.geometry_requirements:
        layer = _resolve_layer(context.state, str(context.action_input.get(slot) or ""))
        if layer is None:
            continue
        geometry = str((layer.metadata or {}).get("geometry_type") or "").lower()
        if geometry and expected not in geometry:
            return [
                _ask_user_issue(
                    "geometry_type_mismatch",
                    "preflight",
                    f"Layer {layer.name} has geometry {geometry}; {context.plan.action} expects a {expected} layer for {slot}.",
                    {"layer": layer.name, "geometry": geometry, "expected": expected, "slot": slot},
                )
            ]
    return []


def _field_requirement_issues(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.state is None:
        return []
    from pineflow_agent.tools.contracts.tool_definitions import tool_definition_for_action

    definition = tool_definition_for_action(context.plan.action)
    if definition is None:
        return []

    for layer_slot, field_slots in definition.field_requirements:
        fields: list[Any] = []
        for field_slot in field_slots:
            value = context.action_input.get(field_slot)
            if isinstance(value, list):
                fields.extend(value)
            elif not _is_missing(value):
                fields.append(value)
        layer = _resolve_layer(context.state, str(context.action_input.get(layer_slot) or ""))
        if layer is None:
            continue
        missing = _missing_fields(layer, fields)
        if missing:
            return [
                _ask_user_issue(
                    "unknown_field",
                    "preflight",
                    f"Layer {layer.name} does not contain field(s): {missing}.",
                    {"layer": layer.name, "fields": missing, "available_fields": _layer_fields(layer)},
                )
            ]
    return []


def _layer_kind_issue(state: GISStateTree, layer_ref: str, expected_kind: str) -> ValidationIssue | None:
    layer = _resolve_layer(state, layer_ref)
    if layer is None:
        return _ask_user_issue(
            "unknown_layer",
            "preflight",
            f"Layer {layer_ref or '<empty>'} was not found. Please choose one of the loaded layers.",
            {"layer": layer_ref or "<empty>"},
        )
    if layer.kind != expected_kind:
        return _ask_user_issue(
            "layer_kind_mismatch",
            "preflight",
            f"Layer {layer.name} is {layer.kind}, but this tool expects {expected_kind}.",
            {"layer": layer.name, "kind": layer.kind, "expected_kind": expected_kind},
        )
    return None


def _normalized_action_input(plan: ActionPlan) -> dict[str, Any]:
    from pineflow_agent.tools.semantic.semantic_tools import is_semantic_action, normalize_semantic_input

    if is_semantic_action(plan.action):
        return normalize_semantic_input(plan.action, plan.action_input)
    return dict(plan.action_input or {})


def _resolve_layer(state: GISStateTree, layer_ref: str) -> LayerRecord | None:
    try:
        return state.resolve(layer_ref)
    except KeyError:
        return None


def _layer_fields(layer: LayerRecord) -> list[str]:
    return field_names(dict(layer.metadata or {}))


def _missing_fields(layer: LayerRecord, fields: list[Any]) -> list[str]:
    available = {field.lower() for field in _layer_fields(layer)}
    missing: list[str] = []
    for field in fields:
        text = str(field or "").strip()
        if text and text.lower() not in available:
            missing.append(text)
    return missing


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _ask_user_issue(code: str, stage: RuleStage, message: str, params: dict[str, Any]) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        stage=stage,
        severity="error",
        message_key=message,
        params=params,
        repair=RepairProposal(kind="ask_user", message_key=message, params=params),
    )
