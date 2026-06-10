"""Factory helpers for agent run results."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.models import AgentResult, ReActStep
from pineflow_agent.risks.models import GISRisk
from pineflow_agent.rules.validation import PendingTask, RepairProposal, ValidationIssue


def completed_result(
    final_message: str,
    *,
    steps: list[ReActStep],
    state_tree: dict[str, Any],
    session_id: str,
) -> AgentResult:
    return AgentResult(
        success=True,
        final_message=final_message,
        steps=steps,
        state=state_tree,
        session_id=session_id,
        status="completed",
    )


def failed_result(
    final_message: str,
    *,
    steps: list[ReActStep],
    state_tree: dict[str, Any],
    session_id: str,
    status: str = "failed",
    errors: list[str] | None = None,
) -> AgentResult:
    return AgentResult(
        success=False,
        final_message=final_message,
        steps=steps,
        state=state_tree,
        session_id=session_id,
        status=status,
        errors=list(errors or []),
    )


def awaiting_result(
    final_message: str,
    *,
    steps: list[ReActStep],
    state_tree: dict[str, Any],
    session_id: str,
    status: str = "awaiting_user",
    issues: list[ValidationIssue] | None = None,
    risks: list[GISRisk] | None = None,
    pending_task: PendingTask | None = None,
    repair: RepairProposal | None = None,
) -> AgentResult:
    return AgentResult(
        success=False,
        final_message=final_message,
        steps=steps,
        state=state_tree,
        session_id=session_id,
        status=status,
        next_question=final_message,
        issues=list(issues or []),
        risks=list(risks or []),
        pending_task=pending_task,
        repair=repair,
    )


def paused_result(
    steps: list[ReActStep],
    *,
    state_tree: dict[str, Any],
    session_id: str,
) -> AgentResult:
    return AgentResult(
        success=False,
        final_message="Paused by user request.",
        steps=steps,
        state=state_tree,
        session_id=session_id,
        status="paused",
    )


def cancelled_result(
    steps: list[ReActStep],
    *,
    state_tree: dict[str, Any],
    session_id: str,
) -> AgentResult:
    return AgentResult(
        success=False,
        final_message="Cancelled by user request.",
        steps=steps,
        state=state_tree,
        session_id=session_id,
        status="cancelled",
    )


def action_selection_error_result(
    error_message: str,
    *,
    steps: list[ReActStep],
    state_tree: dict[str, Any],
    session_id: str,
) -> AgentResult:
    message = (
        "The GIS tool steps completed so far, but the AI could not choose the next action. "
        f"LLM action selection error: {error_message}"
    )
    return failed_result(
        message,
        steps=steps,
        state_tree=state_tree,
        session_id=session_id,
        errors=[f"model_adapter_error: {error_message}"],
    )
