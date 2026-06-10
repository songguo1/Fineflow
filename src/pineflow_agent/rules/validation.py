"""Structured validation issues and repair proposals for GIS actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.messages import render_message

ValidationStage = Literal["semantic", "preflight", "resume", "execution"]
IssueSeverity = Literal["info", "warning", "error"]
RepairKind = Literal["ask_user", "confirm_action", "parameter_patch"]


@dataclass
class RepairProposal:
    kind: RepairKind
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    patch: dict[str, Any] | None = None
    requires_confirmation: bool = False

    @property
    def message(self) -> str:
        return render_message(self.message_key, self.params)

    def action_sequence(self) -> list[dict[str, Any]]:
        if self.steps:
            return [dict(step) for step in self.steps if isinstance(step, dict)]
        if self.action:
            return [dict(self.action)]
        return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message_key": self.message_key,
            "message": self.message,
            "params": make_json_safe(self.params),
            "action": make_json_safe(self.action or {}),
            "steps": make_json_safe(self.action_sequence()),
            "patch": make_json_safe(self.patch or {}),
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass
class ValidationIssue:
    code: str
    stage: ValidationStage
    severity: IssueSeverity
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)
    repair: RepairProposal | None = None

    @property
    def message(self) -> str:
        return render_message(self.message_key, self.params)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "severity": self.severity,
            "message_key": self.message_key,
            "message": self.message,
            "params": make_json_safe(self.params),
            "repair": self.repair.to_dict() if self.repair else None,
        }


@dataclass
class PendingTask:
    active_intent: str
    continue_with: str = ""
    source: str = ""
    pending_kind: str = ""
    filled_slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    original_request: str = ""
    last_question_key: str = ""
    last_question_params: dict[str, Any] = field(default_factory=dict)
    awaiting_state: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    correction_history: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] = field(default_factory=dict)
    risk_code: str = ""
    confirmation_type: str = ""
    choices: list[dict[str, Any]] = field(default_factory=list)
    slot_patch_schema: dict[str, Any] = field(default_factory=dict)
    source_requests: list[dict[str, Any]] = field(default_factory=list)
    ux_explanation: str = ""
    question: str = ""

    @classmethod
    def from_payload(cls, value: Any) -> "PendingTask":
        payload = make_json_safe(dict(value or {})) if isinstance(value, dict) else {}
        missing_slots = [str(slot) for slot in list(payload.get("missing_slots") or []) if str(slot or "").strip()]
        choices = normalize_pending_choices(payload.get("choices"), missing_slots)
        slot_patch_schema = normalize_slot_patch_schema(payload.get("slot_patch_schema"), missing_slots)
        source_requests = [
            make_json_safe(dict(item))
            for item in list(payload.get("source_requests") or [])
            if isinstance(item, dict)
        ]
        question = str(payload.get("question") or payload.get("last_question") or "").strip()
        pending_kind = str(payload.get("pending_kind") or "").strip() or ("choice" if choices else "form")
        active_intent = _canonical_pending_intent(payload)
        continue_with = str(payload.get("continue_with") or payload.get("continueWith") or "").strip()
        if active_intent and (not continue_with or continue_with in {str(payload.get("active_intent") or "").strip(), active_intent}):
            continue_with = _display_title_for_action(active_intent)
        return cls(
            active_intent=active_intent,
            continue_with=continue_with,
            source=str(payload.get("source") or payload.get("pending_source") or ""),
            pending_kind=pending_kind,
            filled_slots=make_json_safe(dict(payload.get("filled_slots") or {})),
            missing_slots=missing_slots,
            original_request=str(payload.get("original_request") or ""),
            last_question_key=str(payload.get("last_question_key") or question),
            last_question_params=make_json_safe(dict(payload.get("last_question_params") or {})),
            awaiting_state=str(payload.get("awaiting_state") or ""),
            allowed_actions=[str(item) for item in list(payload.get("allowed_actions") or []) if str(item or "").strip()],
            correction_history=make_json_safe(list(payload.get("correction_history") or [])),
            risk=make_json_safe(dict(payload.get("risk") or {})) if isinstance(payload.get("risk"), dict) else {},
            risk_code=str(payload.get("risk_code") or ""),
            confirmation_type=str(payload.get("confirmation_type") or ""),
            choices=choices,
            slot_patch_schema=slot_patch_schema,
            source_requests=source_requests,
            ux_explanation=str(payload.get("ux_explanation") or question),
            question=question,
        )

    @property
    def last_question(self) -> str:
        return render_message(self.last_question_key, self.last_question_params)

    def to_dict(self) -> dict[str, Any]:
        missing_slots = list(self.missing_slots)
        slot_patch_schema = normalize_slot_patch_schema(self.slot_patch_schema, missing_slots)
        payload = {
            "source": self.source,
            "pending_kind": self.pending_kind,
            "active_intent": self.active_intent,
            "continue_with": self.continue_with,
            "filled_slots": make_json_safe(self.filled_slots),
            "missing_slots": missing_slots,
            "original_request": self.original_request,
            "last_question_key": self.last_question_key,
            "last_question_params": make_json_safe(self.last_question_params),
            "last_question": self.last_question,
            "awaiting_state": self.awaiting_state,
            "allowed_actions": list(self.allowed_actions),
            "correction_history": make_json_safe(self.correction_history),
            "risk": make_json_safe(dict(self.risk or {})),
            "risk_code": self.risk_code,
            "confirmation_type": self.confirmation_type,
            "choices": make_json_safe(normalize_pending_choices(self.choices, missing_slots)),
            "slot_patch_schema": make_json_safe(slot_patch_schema),
            "source_requests": make_json_safe([dict(item) for item in self.source_requests if isinstance(item, dict)]),
            "ux_explanation": self.ux_explanation,
            "question": self.question or self.last_question,
        }
        payload["schema_version"] = 2
        payload["pending_id"] = _pending_id(payload)
        payload["action_schema"] = _pending_action_schema(payload)
        payload["audit_decision"] = _pending_audit_decision(payload)
        return payload


def slot_patch_schema_for_missing_slots(missing_slots: list[str]) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    for slot in list(missing_slots or []):
        name = str(slot or "").strip()
        if not name:
            continue
        schema[name] = {
            "required": True,
            "type": "array" if name.endswith("_refs") else "string",
        }
    return schema


def normalize_slot_patch_schema(value: Any, missing_slots: list[str]) -> dict[str, Any]:
    defaults = slot_patch_schema_for_missing_slots(missing_slots)
    if not isinstance(value, dict) or not value:
        return defaults
    normalized: dict[str, Any] = {}
    for slot, schema in value.items():
        name = str(slot or "").strip()
        if not name or not isinstance(schema, dict):
            continue
        merged = dict(defaults.get(name) or {})
        merged.update(schema)
        normalized[name] = merged
    for slot, schema in defaults.items():
        normalized.setdefault(slot, dict(schema))
    return normalized


def _pending_id(value: dict[str, Any]) -> str:
    basis = "|".join(
        [
            str(value.get("source") or ""),
            str(value.get("pending_kind") or ""),
            str(value.get("active_intent") or ""),
            str(value.get("question") or ""),
            ",".join(str(item) for item in list(value.get("missing_slots") or [])),
        ]
    )
    return f"pending_{uuid5(NAMESPACE_URL, basis).hex[:16]}"


def _pending_action_schema(value: dict[str, Any]) -> dict[str, Any]:
    allowed = [str(item) for item in list(value.get("allowed_actions") or []) if str(item or "").strip()]
    slot_schema = dict(value.get("slot_patch_schema") or {})
    return make_json_safe(
        {
            "allowed_actions": allowed,
            "actions": {
                "patch": {"slot_patch_schema": slot_schema} if "patch" in allowed else {},
                "confirm": {"decision": "confirm"} if "confirm" in allowed else {},
                "reject": {"decision": "reject"} if "reject" in allowed else {},
                "cancel": {"decision": "cancel"} if "cancel" in allowed else {},
                "replan": {"decision": "replan"} if "replan" in allowed else {},
            },
        }
    )


def _pending_audit_decision(value: dict[str, Any]) -> dict[str, Any]:
    risk = dict(value.get("risk") or {}) if isinstance(value.get("risk"), dict) else {}
    return make_json_safe(
        {
            "pending_id": str(value.get("pending_id") or ""),
            "source": str(value.get("source") or ""),
            "pending_kind": str(value.get("pending_kind") or ""),
            "active_intent": str(value.get("active_intent") or ""),
            "risk_code": str(value.get("risk_code") or risk.get("code") or ""),
            "risk_category": str(value.get("confirmation_type") or risk.get("category") or ""),
            "question": str(value.get("question") or value.get("last_question") or ""),
        }
    )


def normalize_pending_choices(
    choices: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    missing_slots: list[str],
) -> list[dict[str, Any]]:
    slots = [str(slot) for slot in list(missing_slots or []) if str(slot or "").strip()]
    result: list[dict[str, Any]] = []
    for choice in list(choices or []):
        if not isinstance(choice, dict):
            continue
        item = dict(choice)
        slot = str(item.get("slot") or _choice_slot(item, slots)).strip()
        value = _choice_value(item)
        if not slot or not _has_choice_value(value):
            continue
        item["slot"] = slot
        item["value"] = value
        item["label"] = _choice_label(item, value)
        result.append(item)
    return result


def _choice_slot(choice: dict[str, Any], slots: list[str]) -> str:
    if not slots:
        return ""
    if len(slots) == 1:
        slot = slots[0]
        if choice.get("field") and "field" not in slot:
            return ""
        if (choice.get("layer_id") or choice.get("kind") or choice.get("geometry_type")) and not _is_layer_slot(slot):
            return ""
        return slot
    if choice.get("field"):
        for slot in slots:
            if "field" in slot:
                return slot
    if choice.get("layer_id") or choice.get("kind") or choice.get("geometry_type"):
        for slot in slots:
            if _is_layer_slot(slot):
                return slot
        return ""
    if choice.get("field"):
        return ""
    return slots[0]


def _is_layer_slot(slot: str) -> bool:
    return slot.endswith("_ref") or slot.endswith("_refs") or slot in {"layer_ref", "input_ref", "overlay_ref"}


def _choice_value(choice: dict[str, Any]) -> Any:
    if "value" in choice:
        return choice.get("value")
    if _has_choice_value(choice.get("field")):
        return choice.get("field")
    if _has_choice_value(choice.get("layer_id")):
        return choice.get("layer_id")
    return None


def _choice_label(choice: dict[str, Any], value: Any) -> str:
    label = choice.get("label")
    if _has_choice_value(label):
        return str(label)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _has_choice_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, list):
        return bool(value)
    return True


def allowed_resume_actions(status: str) -> list[str]:
    normalized = str(status or "").strip()
    if normalized == "awaiting_confirmation":
        return ["confirm", "reject", "cancel"]
    if normalized == "awaiting_user":
        return ["patch", "cancel", "replan"]
    return []


def _canonical_pending_intent(payload: dict[str, Any]) -> str:
    raw = str(payload.get("active_intent") or "").strip()
    if not raw:
        return ""
    from pineflow_agent.tools.contracts.tool_definitions import canonical_action_for_intent

    resolved = canonical_action_for_intent(raw, context=payload)
    return resolved or raw


def _display_title_for_action(action: str) -> str:
    from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action

    return display_title_for_action(action)


def issues_to_dict(issues: list[ValidationIssue]) -> list[dict[str, Any]]:
    return [issue.to_dict() for issue in issues]
