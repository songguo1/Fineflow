"""Resume decision parsing and pure action application helpers."""

from __future__ import annotations

import json
from typing import Any

from pineflow_agent.core.models import ActionPlan
from pineflow_agent.llm.llm import LLMClient, extract_json_object
from pineflow_agent.llm.prompts import RESUME_SYSTEM_PROMPT, build_resume_prompt
from pineflow_agent.orchestration.resume.export_result_contract import export_result_patch_from_values
from pineflow_agent.tools.contracts.tool_definitions import canonical_action_for_intent


class ResumeDecisionParser:
    """Parse and normalize LLM resume decisions."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def parse(self, *, user_reply: str, pending_task: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        prompt = build_resume_prompt(
            user_reply=user_reply,
            pending_task=pending_task,
            state=state,
        )
        raw = self.llm.complete(system_prompt=RESUME_SYSTEM_PROMPT, user_prompt=prompt)
        try:
            payload = json.loads(extract_json_object(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM did not return valid resume JSON: {raw}") from exc
        if not isinstance(payload, dict):
            raise ValueError("LLM resume decision must be a JSON object.")
        return self.clean(payload, pending_task=pending_task)

    @staticmethod
    def clean(decision: dict[str, Any], *, pending_task: dict[str, Any]) -> dict[str, Any]:
        payload = dict(decision or {})
        mode = str(payload.get("decision") or "").strip()
        if mode not in {"patch_slots", "replan", "ask_again"}:
            return _ask_again(
                pending_task,
                reason=f"Unsupported resume decision: {mode or '<empty>'}.",
            )

        if mode == "patch_slots":
            patch = ResumeActionApplier.clean_slot_patch(payload.get("slot_patch"))
            if not patch:
                return _ask_again(
                    pending_task,
                    reason="The model chose patch_slots but did not provide any schema-ready slot values.",
                )
            payload["slot_patch"] = patch
            return payload

        if mode == "replan":
            payload["action"] = str(payload.get("action") or "").strip()
            if not isinstance(payload.get("action_input"), dict):
                payload["action_input"] = {}
            if not payload["action"]:
                return {
                    "decision": "ask_again",
                    "reason": "The model chose replan but did not provide an executable action.",
                    "message": "Please restate the new GIS task in one complete sentence.",
                }
            return payload

        payload["message"] = _question_message(pending_task, payload.get("message"))
        return payload


class ResumeActionApplier:
    """Convert normalized resume decisions and patches into ActionPlan objects."""

    @staticmethod
    def clean_slot_patch(slot_patch: Any) -> dict[str, Any]:
        if not isinstance(slot_patch, dict):
            slot_patch = {}
        return {
            str(key).strip(): value
            for key, value in dict(slot_patch or {}).items()
            if str(key).strip() and value is not None
        }

    @staticmethod
    def plan_from_slot_patch(
        *,
        pending_task: dict[str, Any],
        slot_patch: dict[str, Any],
        thought: str,
    ) -> ActionPlan:
        action_input = dict(pending_task.get("filled_slots") or {})
        action = canonical_action_for_intent(str(pending_task.get("active_intent") or ""), context=pending_task) or str(
            pending_task.get("active_intent") or ""
        ).strip()
        patch = ResumeActionApplier.clean_slot_patch(slot_patch)
        if action == "export_result":
            patch = export_result_patch_from_values({**action_input, **patch})
        action_input.update(patch)
        return ActionPlan(
            thought=thought,
            action=action,
            action_input=action_input,
        )

    @staticmethod
    def plan_from_replan(decision: dict[str, Any]) -> ActionPlan:
        action_input = dict(decision.get("action_input") or {})
        action = canonical_action_for_intent(str(decision.get("action") or ""), context=action_input) or str(
            decision.get("action") or ""
        ).strip()
        return ActionPlan(
            thought=str(decision.get("reason") or "The user changed the GIS task, so replan from the reply."),
            action=action,
            action_input=action_input,
        )


def _ask_again(pending_task: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "decision": "ask_again",
        "reason": reason,
        "message": _question_message(pending_task),
    }


def _question_message(pending_task: dict[str, Any], value: Any = "") -> str:
    return str(value or pending_task.get("last_question") or "Please clarify the missing parameter.")
