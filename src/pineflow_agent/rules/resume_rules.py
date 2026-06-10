"""Validation rules for structured resume actions."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.models import ActionPlan
from pineflow_agent.rules.rule_registry import RuleEvaluationContext, RuleRegistry
from pineflow_agent.rules.validation import ValidationIssue, allowed_resume_actions


def register_resume_rule(name: str, *actions: str) -> Any:
    return RuleRegistry.register(
        name=name,
        stage="resume",
        actions=tuple(str(action or "").strip() for action in actions if str(action or "").strip()),
    )


def resume_rules():
    return tuple(rule for rule in RuleRegistry.default().rules if rule.stage == "resume")


def validate_resume_action(
    action: str,
    *,
    status: str,
    pending_task: dict[str, Any] | None,
    repair: dict[str, Any] | None = None,
    slot_patch: dict[str, Any] | None = None,
    message: str = "",
    has_session: bool = True,
) -> list[ValidationIssue]:
    return RuleRegistry.default().issues(
        "resume",
        ActionPlan(
            "",
            action,
            {
                "status": status,
                "pending_task": dict(pending_task or {}),
                "repair": dict(repair or {}),
                "slot_patch": dict(slot_patch or {}),
                "message": str(message or ""),
                "has_session": bool(has_session),
            },
        ),
    )


@register_resume_rule("resume_requires_session")
def _resume_requires_session(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.action_input.get("has_session", True):
        return []
    return [_resume_issue("resume_missing_session", "session_id is required for structured resume actions.")]


@register_resume_rule("resume_requires_pending_task")
def _resume_requires_pending_task(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.action_input.get("pending_task"):
        return []
    return [_resume_issue("resume_missing_pending_task", "There is no pending GIS task to resume.")]


@register_resume_rule("resume_action_allowed")
def _resume_action_allowed(context: RuleEvaluationContext) -> list[ValidationIssue]:
    pending_task = dict(context.action_input.get("pending_task") or {})
    if not pending_task:
        return []
    status = str(context.action_input.get("status") or "")
    allowed = list(pending_task.get("allowed_actions") or allowed_resume_actions(status))
    if context.plan.action in allowed:
        return []
    return [
        _resume_issue(
            "resume_action_not_allowed",
            f"Resume action {context.plan.action or '<empty>'} is not allowed while the task is {status}.",
            {"allowed_actions": allowed, "status": status},
        )
    ]


@register_resume_rule("confirm_requires_repair", "confirm")
def _confirm_requires_repair(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.action_input.get("repair"):
        return []
    return [_resume_issue("resume_confirm_missing_repair", "The current pending task has no repair to confirm.")]


@register_resume_rule("patch_requires_values", "patch")
def _patch_requires_values(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if context.action_input.get("slot_patch"):
        return []
    return [_resume_issue("resume_patch_empty", "Structured patch actions require slot_patch values.")]


@register_resume_rule("replan_requires_message", "replan")
def _replan_requires_message(context: RuleEvaluationContext) -> list[ValidationIssue]:
    if str(context.action_input.get("message") or "").strip():
        return []
    return [_resume_issue("resume_replan_empty", "Replan actions require a new GIS request message.")]


def _resume_issue(code: str, message: str, params: dict[str, Any] | None = None) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        stage="resume",
        severity="error",
        message_key=message,
        params=dict(params or {}),
    )
