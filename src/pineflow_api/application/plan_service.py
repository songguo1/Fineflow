"""Application service for execution-before-confirmation plan drafts."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.workspace import WorkspaceContext
from pineflow_agent.orchestration.agent.goal_contract import infer_goal_contract
from pineflow_api.contracts.models import QGISAgentRequest
from pineflow_api.contracts.plans import PlanDraft, PlanPatchRequest
from pineflow_api.persistence.plans import PlanDraftStore


class PlanNotFoundError(RuntimeError):
    """Raised when a plan id is unknown."""


class PlanService:
    """Owns PlanDraft lifecycle and persistence."""

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        workspace: WorkspaceContext | None = None,
        store: PlanDraftStore | None = None,
    ) -> None:
        self._plans: dict[str, PlanDraft] = {}
        self._requests: dict[str, QGISAgentRequest] = {}
        self._store = store or PlanDraftStore(root=root, workspace=workspace)

    def create(self, request: QGISAgentRequest) -> dict:
        plan_id = f"plan_{uuid4().hex}"
        goal_contract = infer_goal_contract(request.message).to_dict()
        plan = PlanDraft(
            plan_id=plan_id,
            session_id=str(request.session_id or ""),
            user_request=request.message,
            goal_contract=goal_contract,
            assumptions=_assumptions(goal_contract),
            approved_assumptions=[],
            risk_preview=_risk_preview(goal_contract),
            expected_outputs=list(goal_contract.get("required_outputs") or []),
            status="draft",
        )
        self._plans[plan_id] = plan
        self._requests[plan_id] = request
        self._save(plan)
        return self.get(plan_id)

    def get(self, plan_id: str) -> dict:
        plan = self._plan(plan_id)
        return make_json_safe(plan.model_dump())

    def approve(self, plan_id: str) -> dict:
        plan = self._plan(plan_id)
        goal_contract = dict(plan.goal_contract or {})
        goal_contract["source"] = "plan_approved"
        plan = plan.model_copy(
            update={
                "status": "approved",
                "goal_contract": goal_contract,
                "approved_at": plan.approved_at or _utc_now(),
                "approved_assumptions": list(plan.approved_assumptions or plan.assumptions or []),
            }
        )
        self._plans[plan.plan_id] = plan
        self._save(plan)
        return self.get(plan.plan_id)

    def reject(self, plan_id: str) -> dict:
        plan = self._plan(plan_id).model_copy(update={"status": "rejected", "rejected_at": _utc_now()})
        self._plans[plan.plan_id] = plan
        self._save(plan)
        return self.get(plan.plan_id)

    def patch(self, plan_id: str, patch: PlanPatchRequest) -> dict:
        plan = self._plan(plan_id)
        if plan.status == "executed":
            raise ValueError("Executed plan cannot be patched.")
        update: dict[str, object] = {}
        if patch.user_request is not None:
            update["user_request"] = patch.user_request
            request = self._requests.get(plan.plan_id)
            if request is not None:
                self._requests[plan.plan_id] = request.model_copy(update={"message": patch.user_request})
        if patch.assumptions is not None:
            update["assumptions"] = list(patch.assumptions)
        if patch.risk_preview is not None:
            update["risk_preview"] = list(patch.risk_preview)
        if patch.expected_outputs is not None:
            update["expected_outputs"] = list(patch.expected_outputs)
        if patch.goal_contract is not None:
            update["goal_contract"] = dict(patch.goal_contract)
        plan = plan.model_copy(update=update)
        self._plans[plan.plan_id] = plan
        self._save(plan)
        return self.get(plan.plan_id)

    def execution_request(self, plan_id: str, request: QGISAgentRequest | None = None) -> QGISAgentRequest:
        plan = self._plan(plan_id)
        if plan.status == "rejected":
            raise ValueError("Rejected plan cannot be executed.")
        if plan.status == "draft":
            self.approve(plan.plan_id)
            plan = self._plan(plan_id)
        base = request or self._requests.get(plan.plan_id)
        if base is None:
            raise PlanNotFoundError("Plan request does not exist.")
        goal_contract = dict(plan.goal_contract or {})
        goal_contract["source"] = "plan_approved"
        plan_context = self.plan_context(plan.plan_id, status="approved", goal_contract=goal_contract)
        options = base.options.model_copy(
            update={
                "plan_id": plan.plan_id,
                "goal_contract": goal_contract,
                "plan_context": plan_context,
            }
        )
        return base.model_copy(update={"session_id": plan.session_id or base.session_id, "options": options})

    def mark_executed(self, plan_id: str, *, run_id: str) -> dict:
        plan = self._plan(plan_id)
        goal_contract = dict(plan.goal_contract or {})
        goal_contract["source"] = "plan_approved"
        plan = plan.model_copy(
            update={
                "status": "executed",
                "goal_contract": goal_contract,
                "executed_at": plan.executed_at or _utc_now(),
                "executed_run_id": str(run_id or ""),
            }
        )
        self._plans[plan.plan_id] = plan
        self._save(plan)
        return self.get(plan.plan_id)

    def plan_context(
        self,
        plan_id: str,
        *,
        status: str = "",
        goal_contract: dict | None = None,
        executed_run_id: str = "",
    ) -> dict:
        plan = self._plan(plan_id)
        return make_json_safe(
            {
                "plan_id": plan.plan_id,
                "session_id": plan.session_id,
                "user_request": plan.user_request,
                "status": status or plan.status,
                "goal_contract": dict(goal_contract or plan.goal_contract or {}),
                "assumptions": list(plan.assumptions or []),
                "approved_assumptions": list(plan.approved_assumptions or plan.assumptions or []),
                "risk_preview": list(plan.risk_preview or []),
                "expected_outputs": list(plan.expected_outputs or []),
                "approved_at": plan.approved_at,
                "rejected_at": plan.rejected_at,
                "executed_at": plan.executed_at,
                "executed_run_id": executed_run_id or plan.executed_run_id,
            }
        )

    def list(self, *, session_id: str = "", status: str = "active", limit: int = 20) -> list[dict]:
        plans = self._store.list(session_id=session_id, status=status, limit=limit)
        for plan in plans:
            normalized_id = str(plan.get("plan_id") or "").strip()
            if normalized_id and normalized_id not in self._plans:
                try:
                    self._plans[normalized_id] = PlanDraft.model_validate(plan)
                except Exception:
                    continue
        return plans

    def _plan(self, plan_id: str) -> PlanDraft:
        normalized = str(plan_id or "").strip()
        plan = self._plans.get(normalized)
        if plan is None:
            restored = self._store.get(normalized)
            if restored is not None:
                plan, request = restored
                self._plans[plan.plan_id] = plan
                if request is not None:
                    self._requests[plan.plan_id] = request
        if plan is None:
            raise PlanNotFoundError("Plan does not exist.")
        return deepcopy(plan)

    def _save(self, plan: PlanDraft) -> None:
        self._store.save(plan, self._requests.get(plan.plan_id))


def _assumptions(goal_contract: dict) -> list[str]:
    constraints = set(str(item or "") for item in list(goal_contract.get("constraints") or []))
    required_outputs = set(str(item or "") for item in list(goal_contract.get("required_outputs") or []))
    assumptions = ["计划只描述分析目标和风险，不固定 QGIS 工具执行顺序。"]
    if "distance_or_buffer_analysis" in constraints:
        assumptions.append("涉及距离或面积的操作需要确认输入 CRS 是否适合量算。")
    if "selection_or_filter_constraint" in constraints:
        assumptions.append("字段名、字段类型和筛选口径需要以当前图层属性表为准。")
    if "final_gis_output" in required_outputs:
        assumptions.append("最终输出路径和覆盖策略会在执行阶段按运行时状态确认。")
    return assumptions


def _risk_preview(goal_contract: dict) -> list[dict]:
    constraints = set(str(item or "") for item in list(goal_contract.get("constraints") or []))
    required_outputs = set(str(item or "") for item in list(goal_contract.get("required_outputs") or []))
    risks: list[dict] = []
    if "distance_or_buffer_analysis" in constraints:
        risks.append(
            {
                "code": "crs_distance_preview",
                "severity": "warning",
                "message": "距离/缓冲分析可能需要投影 CRS；执行时会由 preflight/runtime 再做正式判断。",
            }
        )
    if "selection_or_filter_constraint" in constraints:
        risks.append(
            {
                "code": "field_ambiguity_preview",
                "severity": "info",
                "message": "字段选择可能存在歧义；执行中如无法确定会主动澄清。",
            }
        )
    if "final_gis_output" in required_outputs:
        risks.append(
            {
                "code": "output_overwrite_preview",
                "severity": "info",
                "message": "导出位置和覆盖风险会在真正写文件前检查。",
            }
        )
    return risks


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
