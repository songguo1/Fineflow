"""MetaToolDispatcher — single dispatch table for all meta/runtime tools.

Keeps the main ReAct loop thin.  A *meta tool* is any tool whose execution does
not go through `ToolRegistry.execute()` and whose run-loop behaviour
(validation, step counting, event emission) differs from standard GIS tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pineflow_agent.core.models import Observation
from pineflow_agent.orchestration.meta.meta_tools import (
    inspect_workspace_observation,
    load_skill_observation,
    proactive_clarification_observation,
    select_toolkit_observation,
    suggest_skill_observation,
)


class MetaToolExecutor(Protocol):
    """Callable that executes a meta tool and returns an Observation."""

    def __call__(self, __dispatcher: "MetaToolDispatcher", __action_input: dict[str, Any]) -> Observation:
        ...


@dataclass(frozen=True)
class MetaToolDef:
    name: str
    executor: MetaToolExecutor
    consumes_step: bool = True
    skip_validation: bool = True
    continue_after_success: bool = True
    fail_is_hard: bool = True


@dataclass
class MetaToolDispatcher:
    """Owns the meta-tool dispatch table and contextual references."""

    tool_disclosure: Any = None
    toolbox: Any = None
    tool_registry: Any = None
    state: Any = None
    steps: list[Any] = field(default_factory=list)
    session_id: str = ""
    user_request: str = ""

    _table: dict[str, MetaToolDef] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._table = {
            "select_toolkit": MetaToolDef(
                name="select_toolkit",
                executor=self._exec_select_toolkit,
            ),
            "inspect_workspace": MetaToolDef(
                name="inspect_workspace",
                executor=self._exec_inspect_workspace,
            ),
            "suggest_skill": MetaToolDef(
                name="suggest_skill",
                executor=self._exec_suggest_skill,
            ),
            "load_skill": MetaToolDef(
                name="load_skill",
                executor=self._exec_load_skill,
            ),
            "proactive_clarification": MetaToolDef(
                name="proactive_clarification",
                executor=self._exec_proactive_clarification,
                continue_after_success=False,
            ),
        }

    # ── public API ───────────────────────────────────────────────────────

    def is_meta(self, action: str) -> bool:
        return action in self._table

    def definition(self, action: str) -> MetaToolDef | None:
        return self._table.get(action)

    def execute(self, action: str, action_input: dict[str, Any]) -> Observation:
        """Dispatch *action* to the registered meta-tool executor."""
        meta = self._table.get(action)
        if meta is None:
            return Observation(status="error", message=f"Meta tool '{action}' is not registered.")
        return meta.executor(self, dict(action_input or {}))

    @property
    def prompt_catalog(self) -> dict[str, Any]:
        if self.tool_disclosure is not None and hasattr(self.tool_disclosure, "prompt_catalog"):
            return self.tool_disclosure.prompt_catalog(self.tool_registry or ())
        return {}

    # ── executors ────────────────────────────────────────────────────────

    def _exec_select_toolkit(self, dispatcher: MetaToolDispatcher, action_input: dict) -> Observation:
        return select_toolkit_observation(dispatcher.tool_disclosure, action_input)

    def _exec_inspect_workspace(self, dispatcher: MetaToolDispatcher, action_input: dict) -> Observation:
        return inspect_workspace_observation(
            dispatcher.tool_disclosure,
            state=dispatcher.state,
            action_input=action_input,
            tool_registry=dispatcher.tool_registry,
            toolbox=dispatcher.toolbox,
            steps=dispatcher.steps,
            session_id=dispatcher.session_id,
        )

    def _exec_suggest_skill(self, dispatcher: MetaToolDispatcher, action_input: dict) -> Observation:
        return suggest_skill_observation(action_input, default_query=dispatcher.user_request)

    def _exec_load_skill(self, dispatcher: MetaToolDispatcher, action_input: dict) -> Observation:
        return load_skill_observation(dispatcher.toolbox, action_input, dispatcher.tool_disclosure)

    def _exec_proactive_clarification(self, dispatcher: MetaToolDispatcher, action_input: dict) -> Observation:
        return proactive_clarification_observation(action_input, default_request=dispatcher.user_request)
