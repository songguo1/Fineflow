"""Factories for agent and QGIS runtime objects used by turn execution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from pineflow_agent.orchestration.agent.react_loop import ReActGISAgent
from pineflow_agent.tools.qgis.toolbox import QGISToolbox
from pineflow_runtime.runtime import QGISRuntime

from pineflow_api.application.execution import build_agent as shared_build_agent
from pineflow_api.application.qgis_runtime_proxy import SubprocessQGISRuntime
from pineflow_api.application.run_runtime import RunManager
from pineflow_api.contracts.models import QGISAgentRequest


class AgentRuntimeFactoryService:
    """Builds agent and runtime instances for routed turn execution."""

    def __init__(
        self,
        *,
        run_manager: RunManager,
        agent_cls: type[ReActGISAgent] | None = None,
        qgis_runtime_cls: type[QGISRuntime] | None = None,
        subprocess_runtime_cls: type[SubprocessQGISRuntime] | None = None,
    ) -> None:
        self.run_manager = run_manager
        self.agent_cls = agent_cls or ReActGISAgent
        self.qgis_runtime_cls = qgis_runtime_cls or QGISRuntime
        self.subprocess_runtime_cls = subprocess_runtime_cls or SubprocessQGISRuntime

    def build_agent(self, request: QGISAgentRequest, toolbox: QGISToolbox) -> ReActGISAgent:
        return shared_build_agent(
            request,
            toolbox,
            agent_cls=self.agent_cls,
            should_pause=self.run_manager.should_pause_session,
            should_cancel=self.run_manager.should_cancel_session,
        )

    def runtime_factory_for_request(self, request: QGISAgentRequest) -> Callable[..., Any]:
        launcher = str(request.qgis.launcher or "").strip()
        prefix_path = str(request.qgis.prefix_path or "").strip()
        use_proxy = (
            os.environ.get("QGIS_AGENT_FORCE_IN_PROCESS") != "1"
            and bool(launcher)
            and Path(launcher).exists()
        )
        if use_proxy:
            return lambda **kwargs: self.subprocess_runtime_cls(
                launcher=launcher,
                prefix_path=str(kwargs.get("prefix_path") or prefix_path or ""),
            )
        return lambda **kwargs: self.qgis_runtime_cls(
            prefix_path=str(kwargs.get("prefix_path") or prefix_path or "") or None
        )

    @staticmethod
    def apply_qgis_environment(request: QGISAgentRequest) -> None:
        launcher = str(request.qgis.launcher or "").strip()
        if request.qgis.prefix_path and (os.environ.get("QGIS_AGENT_FORCE_IN_PROCESS") == "1" or not launcher):
            os.environ["QGIS_PREFIX_PATH"] = request.qgis.prefix_path
