"""Pending task contract helpers."""

from __future__ import annotations

from typing import Any
from uuid import uuid5, NAMESPACE_URL

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.rules.validation import normalize_pending_choices, normalize_slot_patch_schema, slot_patch_schema_for_missing_slots


def normalize_pending_task(value: Any) -> dict[str, Any]:
    """Return a JSON-safe pending task while preserving legacy fields."""
    if not isinstance(value, dict) or not value:
        return {}
    payload = make_json_safe(dict(value))
    normalized = dict(payload)
    normalized["schema_version"] = int(payload.get("schema_version") or 2)
    normalized["source"] = str(payload.get("source") or payload.get("pending_source") or "")
    normalized["pending_kind"] = str(payload.get("pending_kind") or payload.get("confirmation_type") or "")
    normalized["active_intent"] = _canonical_active_intent(payload)
    normalized["continue_with"] = _normalize_continue_with(payload, normalized["active_intent"])
    normalized["question"] = str(payload.get("question") or payload.get("last_question") or "")
    normalized["awaiting_state"] = str(payload.get("awaiting_state") or "")
    normalized["allowed_actions"] = _list(payload.get("allowed_actions"))
    normalized["pending_id"] = str(payload.get("pending_id") or _pending_id(normalized))
    normalized["risk"] = make_json_safe(dict(payload.get("risk") or {})) if isinstance(payload.get("risk"), dict) else {}
    missing_slots = [str(slot) for slot in _list(payload.get("missing_slots")) if str(slot or "").strip()]
    normalized["missing_slots"] = missing_slots
    normalized["choices"] = normalize_pending_choices(_list(payload.get("choices")), missing_slots)
    provided_schema = payload.get("slot_patch_schema")
    normalized["slot_patch_schema"] = normalize_slot_patch_schema(provided_schema, missing_slots)
    normalized["source_requests"] = [
        make_json_safe(dict(item))
        for item in _list(payload.get("source_requests"))
        if isinstance(item, dict)
    ]
    normalized["action_schema"] = _action_schema(normalized)
    normalized["audit_decision"] = _audit_decision(normalized)
    return make_json_safe(normalized)


def _list(value: Any) -> list[Any]:
    return make_json_safe(list(value or [])) if isinstance(value, list) else []


def _canonical_active_intent(payload: dict[str, Any]) -> str:
    raw = str(payload.get("active_intent") or "").strip()
    if not raw:
        return ""
    from pineflow_agent.tools.contracts.tool_definitions import canonical_action_for_intent

    resolved = canonical_action_for_intent(raw, context=payload)
    return resolved or raw


def _normalize_continue_with(payload: dict[str, Any], active_intent: str) -> str:
    continue_with = str(payload.get("continue_with") or payload.get("continueWith") or "").strip()
    raw_intent = str(payload.get("active_intent") or "").strip()
    if active_intent and (not continue_with or continue_with in {raw_intent, active_intent}):
        from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action

        return display_title_for_action(active_intent)
    return continue_with


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


def _action_schema(value: dict[str, Any]) -> dict[str, Any]:
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


def _audit_decision(value: dict[str, Any]) -> dict[str, Any]:
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
