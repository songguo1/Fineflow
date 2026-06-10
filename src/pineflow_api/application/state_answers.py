"""State-backed answers for non-execution GIS questions."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.json_safety import make_json_safe

from pineflow_api.application.state_answer_formatter import StateAnswerFormatter
from pineflow_api.application.state_query import StateQueryService
from pineflow_api.persistence.session_state import SessionState
from pineflow_api.routing.turn_intent import AnswerType, TurnIntent


class StateAnswerService:
    """Answer read-only questions from persisted session state."""

    def __init__(
        self,
        *,
        query: StateQueryService | None = None,
        formatter: StateAnswerFormatter | None = None,
    ) -> None:
        self.query = query or StateQueryService()
        self.formatter = formatter or StateAnswerFormatter()

    def answer(self, answer_type: AnswerType, session_state: SessionState) -> str:
        return self.formatter.format(self.query.query(answer_type, session_state))


class TurnResponseBuilder:
    """Build result payloads for turns that should not enter ReAct."""

    def __init__(self, *, answers: StateAnswerService | None = None) -> None:
        self.answers = answers or StateAnswerService()

    def build(self, intent: TurnIntent, *, session_id: str, session_state: SessionState) -> dict[str, Any]:
        if intent.kind == "chat":
            return _result_payload(
                session_id=session_id,
                final_message=_chat_message(intent),
                session_state=session_state,
            )
        if intent.kind == "gis_answer":
            return _result_payload(
                session_id=session_id,
                final_message=self.answers.answer(intent.answer_type, session_state),
                session_state=session_state,
            )
        if intent.kind == "session_control":
            return self._session_control_payload(intent, session_id=session_id, session_state=session_state)
        raise ValueError(f"Unsupported non-execution intent: {intent.kind}")

    @staticmethod
    def _session_control_payload(intent: TurnIntent, *, session_id: str, session_state: SessionState) -> dict[str, Any]:
        if intent.control_action == "reset":
            return _result_payload(
                session_id=session_id,
                final_message="会话已重置。可以直接告诉我下一步要处理的数据或 GIS 任务。",
                session_state=session_state,
                state_tree={},
                react_trace=[],
                outputs=[],
            )
        return _result_payload(
            session_id=session_id,
            final_message="当前没有正在等待确认或补充参数的任务。",
            session_state=session_state,
        )


def _result_payload(
    *,
    session_id: str,
    final_message: str,
    session_state: SessionState,
    state_tree: dict[str, Any] | None = None,
    react_trace: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    state = make_json_safe(dict(session_state.state_tree if state_tree is None else state_tree))
    trace = make_json_safe(list([] if react_trace is None else react_trace))
    output_items = make_json_safe(list(StateQueryService().outputs(session_state, state) if outputs is None else outputs))
    return {
        "session_id": session_id,
        "status": status,
        "success": status == "completed",
        "final_message": final_message,
        "react_trace": trace,
        "state_tree": state,
        "outputs": output_items,
        "logs": [],
        "errors": [],
        "next_question": "",
        "issues": [],
        "risks": [],
        "pending_task": {},
        "repair": {},
        "transcript": {},
        "file_state": make_json_safe(dict(session_state.file_state)),
    }


def _chat_message(intent: TurnIntent) -> str:
    return (
        str(intent.message or "").strip()
        or "我在。可以继续告诉我你要做的 GIS 操作，或者问我当前会话里的图层、字段和输出结果。"
    )
