"""Application-level intent resolution before GIS run execution."""

from __future__ import annotations

from typing import Any, Callable

from pineflow_api.application.execution import build_llm
from pineflow_api.contracts.models import QGISAgentRequest
from pineflow_api.routing.command_router import CommandRouter
from pineflow_api.routing.triage_router import TriageRouter
from pineflow_api.routing.turn_intent import TurnIntent
from pineflow_api.routing.turn_routing import TurnRoute


class TurnIntentService:
    """Resolves slash commands and LLM triage into non-execution intents."""

    def __init__(
        self,
        *,
        command_router: CommandRouter | None = None,
        triage_router: TriageRouter | None = None,
        llm_factory: Callable[[QGISAgentRequest], Any] = build_llm,
    ) -> None:
        self.command_router = command_router or CommandRouter()
        self.triage_router = triage_router or TriageRouter()
        self.llm_factory = llm_factory

    def resolve(self, route: TurnRoute, request: QGISAgentRequest) -> TurnIntent | None:
        if route.kind not in {"new_session", "continue_session"}:
            return None
        if request.options.reset_session:
            return None
        command = self.command_router.match(request.message)
        if command is not None:
            intent = command.intent
        else:
            intent = self.triage_router.classify(
                request.message,
                route.session_state,
                llm=self._build_triage_llm(request),
            )
            intent = self._guard_session_control_intent(intent, request.message)
        if intent.kind == "gis_execute":
            return None
        return intent

    def _build_triage_llm(self, request: QGISAgentRequest) -> Any:
        try:
            return self.llm_factory(request)
        except Exception:
            return None

    @staticmethod
    def _guard_session_control_intent(intent: TurnIntent, message: str) -> TurnIntent:
        if intent.kind != "session_control":
            return intent
        action = str(intent.control_action or "").strip()
        text = str(message or "").strip().lower()
        if action == "reset" and not _looks_like_explicit_reset(text):
            return TurnIntent(
                "gis_execute",
                reason=f"guarded_ambiguous_reset:{intent.reason}",
                confidence=intent.confidence,
            )
        if action == "cancel" and not _looks_like_explicit_cancel(text):
            return TurnIntent(
                "gis_execute",
                reason=f"guarded_ambiguous_cancel:{intent.reason}",
                confidence=intent.confidence,
            )
        return intent


def _looks_like_explicit_reset(text: str) -> bool:
    exact = {
        "reset",
        "new",
        "重置",
        "新建会话",
        "重新开始",
        "清空会话",
        "重置会话",
        "清空当前会话",
        "重置当前会话",
    }
    if text in exact:
        return True
    return any(token in text for token in ("reset session", "clear session", "重置会话", "清空会话"))


def _looks_like_explicit_cancel(text: str) -> bool:
    exact = {
        "cancel",
        "stop",
        "取消",
        "停止",
        "取消任务",
        "停止任务",
        "取消当前任务",
        "停止当前任务",
    }
    if text in exact:
        return True
    return any(token in text for token in ("cancel task", "stop task", "取消任务", "停止任务"))
