"""Shared types for API-level turn intent routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TurnIntentKind = Literal["chat", "gis_answer", "gis_execute", "session_control"]
AnswerType = Literal["fields", "layers", "crs", "outputs", "last_step", "summary", "none"]


@dataclass(frozen=True)
class TurnIntent:
    kind: TurnIntentKind
    reason: str = ""
    answer_type: AnswerType = "none"
    control_action: str = ""
    confidence: float = 1.0
    message: str = ""
