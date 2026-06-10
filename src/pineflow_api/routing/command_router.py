"""Deterministic slash-command routing before the GIS ReAct runtime."""

from __future__ import annotations

from dataclasses import dataclass

from pineflow_api.routing.turn_intent import AnswerType, TurnIntent


@dataclass(frozen=True)
class CommandRoute:
    command: str
    intent: TurnIntent


class CommandRouter:
    """Route explicit gateway commands such as /fields and /outputs."""

    def match(self, message: str) -> CommandRoute | None:
        text = str(message or "").strip()
        if not text.startswith("/"):
            return None
        command = text[1:].split(maxsplit=1)[0].strip().lower()
        if not command:
            return None
        answer_type = COMMAND_ANSWERS.get(command)
        if answer_type:
            return CommandRoute(
                command=command,
                intent=TurnIntent(
                    kind="gis_answer",
                    answer_type=answer_type,
                    reason="slash_command",
                    confidence=1.0,
                ),
            )
        control_action = COMMAND_CONTROLS.get(command)
        if control_action:
            return CommandRoute(
                command=command,
                intent=TurnIntent(
                    kind="session_control",
                    control_action=control_action,
                    reason="slash_command",
                    confidence=1.0,
                ),
            )
        return None


COMMAND_ANSWERS: dict[str, AnswerType] = {
    "status": "summary",
    "summary": "summary",
    "layers": "layers",
    "fields": "fields",
    "crs": "crs",
    "outputs": "outputs",
    "last": "last_step",
}

COMMAND_CONTROLS = {
    "reset": "reset",
    "new": "reset",
    "cancel": "cancel",
}
