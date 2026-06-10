"""Plan Mode API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pineflow_api.contracts.models import QGISAgentRequest

PlanStatus = Literal["draft", "approved", "rejected", "executed"]


class PlanCreateRequest(BaseModel):
    request: QGISAgentRequest


class PlanPatchRequest(BaseModel):
    user_request: str | None = None
    assumptions: list[str] | None = None
    risk_preview: list[dict[str, Any]] | None = None
    expected_outputs: list[str] | None = None
    goal_contract: dict[str, Any] | None = None


class PlanDraft(BaseModel):
    plan_id: str
    session_id: str = ""
    user_request: str
    goal_contract: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    approved_assumptions: list[str] = Field(default_factory=list)
    risk_preview: list[dict[str, Any]] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    status: PlanStatus = "draft"
    approved_at: str = ""
    rejected_at: str = ""
    executed_at: str = ""
    executed_run_id: str = ""


class PlanRunRequest(BaseModel):
    request: QGISAgentRequest | None = None
