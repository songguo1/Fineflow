"""Shared execution helpers for in-process and subprocess agent runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from pineflow_agent.core.messages import get_locale
from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action
from pineflow_agent.core.models import ActionPlan
from pineflow_agent.llm.llm import OpenAICompatibleLLM
from pineflow_agent.orchestration.agent.react_loop import ReActGISAgent
from pineflow_agent.tools.qgis.toolbox import QGISToolbox

from pineflow_api.config import default_llm_base_url, default_llm_model, default_llm_provider

EventSink = Callable[[dict[str, Any]], None]


class RuleProviderStubLLM:
    """Test/local stub used when request.llm.provider == 'rule'."""

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        raise ValueError("rule provider does not implement complete(); inject a test LLM or agent stub.")

    def complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        del system_prompt, user_prompt
        raise ValueError("rule provider does not implement complete_text(); inject a test LLM or agent stub.")

    def tool_call(self, *, system_prompt: str, user_prompt: str, tools: list[dict[str, Any]]) -> ActionPlan:
        del system_prompt, user_prompt, tools
        raise ValueError("rule provider does not implement tool_call(); inject a test LLM or agent stub.")


def build_agent(
    request: Any,
    toolbox: QGISToolbox,
    *,
    agent_cls: type[ReActGISAgent] = ReActGISAgent,
    should_pause: Callable[[str], bool] | None = None,
    should_cancel: Callable[[str], bool] | None = None,
) -> ReActGISAgent:
    options = request.options
    return agent_cls(
        llm=build_llm(request),
        toolbox=toolbox,
        auto_repair=bool(options.auto_repair),
        tool_profile=str(options.tool_profile or "vector_raster_basic"),
        tool_allow=list(options.tool_allow or []),
        tool_deny=list(options.tool_deny or []),
        should_pause=should_pause,
        should_cancel=should_cancel,
    )


def build_llm(request: Any) -> Any:
    llm_config = request.llm
    provider = str(llm_config.provider or default_llm_provider()).strip().lower()
    if provider == "rule":
        return RuleProviderStubLLM()
    llm_params = dict(llm_config.llm_params or {})
    return OpenAICompatibleLLM(
        api_key=str(llm_config.api_key or ""),
        base_url=str(llm_config.base_url or default_llm_base_url()),
        model=str(llm_config.model or default_llm_model()),
        provider=provider,
        temperature=float(llm_params.get("temperature", 0.0)),
        extra_params={key: value for key, value in llm_params.items() if key != "temperature"},
    )


def preload_sources(
    toolbox: QGISToolbox,
    request: Any,
    emit: EventSink,
    *,
    skip_existing: bool = False,
    context: dict[str, Any] | None = None,
) -> list[str]:
    logs: list[str] = []
    for source in list(request.sources or []):
        source_type = str(source.type or "vector")
        alias = str(source.alias or "")
        path = str(source.path or "")
        if skip_existing and source_already_loaded(toolbox, path=path, alias=alias):
            continue
        if source_type == "raster":
            observation = toolbox.load_raster(path, name=alias)
        elif source_type == "csv":
            observation = toolbox.load_csv(path, name=alias)
        else:
            observation = toolbox.load_vector(path, name=alias)
        emit(_source_loaded_event(source=source.model_dump(), observation=observation.to_dict(), state_tree=toolbox.state.to_dict(), context=context))
        logs.append(observation.message)
        if not observation.is_success:
            raise RuntimeError(observation.message)
    return logs


def source_already_loaded(toolbox: QGISToolbox, *, path: str, alias: str = "") -> bool:
    target_path = normalized_path_key(path)
    target_alias = str(alias or "").strip()
    for layer in list(toolbox.state.to_dict().get("layers") or []):
        if not isinstance(layer, dict):
            continue
        source_path = normalized_path_key(str(layer.get("source") or ""))
        if source_path != target_path:
            continue
        if target_alias and str(layer.get("name") or "") != target_alias:
            continue
        return True
    return False


def normalized_path_key(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).resolve()).lower()
    except OSError:
        return raw.lower()


def _source_loaded_event(
    *,
    source: dict[str, Any],
    observation: dict[str, Any],
    state_tree: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(source or {})
    preload = dict(context or {})
    source_type = str(payload.get("type") or "vector").strip().lower()
    action = _load_action_for_source_type(source_type)
    alias = str(payload.get("alias") or Path(str(payload.get("path") or "")).stem or "").strip()
    summary = _source_loaded_summary(payload, preload)
    title = _source_loaded_title(preload, action)
    transcript_item = {
        "type": "workflow_step",
        "tool": action,
        "event_type": "source.loaded",
        "display_title": title,
        "display_summary": summary,
        "status": "success",
        "parameters": {"name": alias} if alias else {},
        "parameter_labels": {"name": "名称" if get_locale() == "zh-CN" else "Name"},
        "summary": summary,
        "data": {
            "source": payload,
            "preload_context": preload,
            "resumed_action": str(preload.get("active_intent") or ""),
        },
    }
    return {
        "event": "observe",
        "message": summary or str(observation.get("message") or ""),
        "action": action,
        "source": payload,
        "observation": observation,
        "state_tree": state_tree,
        "display_title": title,
        "display_summary": summary,
        "preload_context": preload,
        "transcript_item": transcript_item,
    }


def _source_loaded_title(preload: dict[str, Any], action: str) -> str:
    phase = str(preload.get("phase") or "").strip()
    if phase == "resume":
        return "补充数据并恢复" if get_locale() == "zh-CN" else "Attach data and resume"
    if phase == "continue_session":
        return "加载新增数据" if get_locale() == "zh-CN" else "Load additional data"
    return display_title_for_action(action)


def _source_loaded_summary(source: dict[str, Any], preload: dict[str, Any]) -> str:
    source_type = str(source.get("type") or "vector").strip().lower()
    alias = str(source.get("alias") or Path(str(source.get("path") or "")).stem or "").strip()
    source_label = _source_type_label(source_type)
    phase = str(preload.get("phase") or "").strip()
    request = _matching_source_request(preload, source_type)
    slot_label = str(request.get("slot_label") or "").strip()
    intent_title = display_title_for_action(str(preload.get("active_intent") or ""))
    if phase == "resume":
        if slot_label and intent_title:
            return f"已补充{source_label}{alias}，用于{slot_label}，继续执行{intent_title}。"
        if intent_title:
            return f"已补充{source_label}{alias}，继续执行{intent_title}。"
        return f"已补充{source_label}{alias}，继续当前任务。"
    if phase == "continue_session":
        return f"已加载新增{source_label}{alias}，继续当前会话。"
    return f"已加载{source_label}{alias}。"


def _matching_source_request(preload: dict[str, Any], source_type: str) -> dict[str, Any]:
    requests = [dict(item) for item in list(preload.get("source_requests") or []) if isinstance(item, dict)]
    for item in requests:
        accepted = [str(value or "").strip().lower() for value in list(item.get("accepted_source_types") or [])]
        if source_type and source_type in accepted:
            return item
    return requests[0] if requests else {}


def _source_type_label(source_type: str) -> str:
    labels = {
        "zh-CN": {
            "vector": "矢量数据 ",
            "raster": "栅格数据 ",
            "csv": "CSV 表格 ",
        },
        "en-US": {
            "vector": "vector data ",
            "raster": "raster data ",
            "csv": "CSV table ",
        },
    }
    locale = get_locale()
    return labels.get(locale, labels["zh-CN"]).get(source_type, "")


def _load_action_for_source_type(source_type: str) -> str:
    return {
        "raster": "load_raster",
        "csv": "load_csv",
    }.get(source_type, "load_vector")
