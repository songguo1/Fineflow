from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

_PREVIOUS_HINTS = (
    "前的结果",
    "之前的结果",
    "前一步结果",
    "上一步前",
    "之前",
    "前一版",
)

_LATEST_INPUT_HINTS = (
    "刚补进来的数据",
    "刚补的数据",
    "新补的数据",
    "新加载的数据",
    "刚加载的数据",
    "补充的数据",
)

_OPERATION_HINTS = {
    "buffer": ("缓冲", "buffer"),
    "csv_points": ("csv转点", "转点", "点图层", "points", "point"),
    "filter": ("筛选", "extract", "clip", "intersect", "located", "裁剪"),
    "export": ("导出", "export", "最终", "输出"),
    "boundary": ("边界", "boundary"),
}

_ACTION_GROUPS = {
    "buffer": ("buffer_layer", "native:buffer", "buffer"),
    "csv_points": ("csv_to_points", "native:createpointslayerfromtable", "createpointslayerfromtable"),
    "filter": (
        "extract_by_location",
        "extract_by_attribute",
        "clip_layer",
        "intersect_layer",
        "join_by_location",
        "native:extractbylocation",
        "native:extractbyattribute",
        "native:clip",
        "native:intersection",
        "extract",
        "clip",
        "intersect",
    ),
    "export": ("export_result",),
}


@dataclass(frozen=True)
class LayerReferenceQuery:
    text: str = ""
    operation: str = ""
    distance: float | None = None
    relation: str = "self"
    role: str = ""


@dataclass(frozen=True)
class LayerReferenceCandidate:
    layer_id: str
    name: str = ""
    score: int = 0
    role: str = ""
    source_action: str = ""
    source_step: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "name": self.name,
            "score": self.score,
            "role": self.role,
            "source_action": self.source_action,
            "source_step": self.source_step,
        }


@dataclass(frozen=True)
class LayerReferenceResolution:
    best_layer_id: str | None = None
    candidates: list[LayerReferenceCandidate] = None  # type: ignore[assignment]
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if self.candidates is None:
            object.__setattr__(self, "candidates", [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_layer_id": self.best_layer_id,
            "ambiguous": self.ambiguous,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


class LayerReferencePhraseParser:
    """Translate user-facing reference phrases into a small structured query."""

    def parse(self, layer_ref: str) -> LayerReferenceQuery:
        text = _normalize_text(layer_ref)
        if not text:
            return LayerReferenceQuery()
        if any(hint in text for hint in _LATEST_INPUT_HINTS):
            return LayerReferenceQuery(text=text, relation="latest", role="input")
        relation = "predecessor" if any(hint in text for hint in _PREVIOUS_HINTS) else "self"
        clean_text = _strip_previous_hints(text)
        return LayerReferenceQuery(
            text=clean_text,
            operation=_operation_from_text(clean_text),
            distance=_distance_value(clean_text),
            relation=relation,
            role="final" if _operation_from_text(clean_text) == "export" else "",
        )


class ArtifactGraphResolver:
    """Resolve structured layer references from state-tree records and artifact lineage."""

    def __init__(self, records: list[Any]) -> None:
        self.records = list(records or [])

    def resolve(self, query: LayerReferenceQuery) -> str | None:
        return self.resolve_with_report(query).best_layer_id

    def resolve_with_report(self, query: LayerReferenceQuery) -> LayerReferenceResolution:
        if not query.text and not query.operation and not query.role:
            return LayerReferenceResolution()
        if query.relation == "latest" and query.role:
            latest = self._latest_role_record(query.role)
            if latest is None:
                return LayerReferenceResolution()
            candidate = _candidate_for_record(latest, score=100)
            return LayerReferenceResolution(best_layer_id=candidate.layer_id, candidates=[candidate], ambiguous=False)

        ranked = sorted(
            (
                (self._score_record(query, record), _source_step(record), index, record)
                for index, record in enumerate(self.records)
            ),
            key=lambda item: (item[0], item[1], item[2]),
            reverse=True,
        )
        if not ranked:
            return LayerReferenceResolution()
        best_score, _, _, best_record = ranked[0]
        if best_score < 2:
            return LayerReferenceResolution()
        scored_candidates = [
            _candidate_for_record(record, score=score)
            for score, _, _, record in ranked
            if score >= 2
        ]
        if query.relation == "predecessor":
            input_layer_ids = _input_layer_ids(best_record)
            if input_layer_ids:
                return LayerReferenceResolution(
                    best_layer_id=input_layer_ids[0],
                    candidates=scored_candidates,
                    ambiguous=_is_ambiguous(scored_candidates),
                )
        return LayerReferenceResolution(
            best_layer_id=_record_layer_id(best_record),
            candidates=scored_candidates,
            ambiguous=_is_ambiguous(scored_candidates),
        )

    def _score_record(self, query: LayerReferenceQuery, record: Any) -> int:
        facts = _record_facts(record)
        text = _candidate_text(record)
        name = _normalize_text(str(getattr(record, "name", "") or ""))
        title = _normalize_text(" ".join(_action_title(action) for action in facts.actions))
        score = 0

        if query.text:
            if name and query.text == name:
                score += 10
            if text and query.text in text:
                score += 6
            if name and name in query.text:
                score += 4
            if title and title in query.text:
                score += 4

        if query.operation and _record_matches_group(facts, query.operation):
            score += 5
        if query.operation == "boundary" and _looks_boundary_related(text):
            score += 2
        if query.distance is not None and _record_distance_matches(record, query.distance):
            score += 5
        if query.role and facts.role == query.role:
            score += 4
        if query.role == "final" and _is_final_record(record):
            score += 4
        if facts.role == "final":
            score += 1
        if facts.source_step is not None:
            score += 1
        return score

    def _latest_role_record(self, role: str) -> Any | None:
        role = str(role or "").strip().lower()
        matches = [record for record in self.records if _record_facts(record).role == role]
        if not matches:
            return None
        return sorted(matches, key=lambda item: (_source_step(item), self.records.index(item)), reverse=True)[0]


def resolve_layer_phrase(layer_ref: str, records: list[Any]) -> str | None:
    """Compatibility entrypoint for string layer references."""

    query = LayerReferencePhraseParser().parse(layer_ref)
    return ArtifactGraphResolver(records).resolve(query)


@dataclass(frozen=True)
class _RecordFacts:
    actions: list[str]
    role: str = ""
    source_step: int | None = None


def _candidate_text(record: Any) -> str:
    metadata = dict(getattr(record, "metadata", None) or {})
    artifact = dict(metadata.get("artifact") or {})
    lineage = _lineage(record)
    parameters = dict(getattr(record, "parameters", None) or {})
    actions = _record_facts(record).actions
    parts = [
        getattr(record, "layer_id", ""),
        getattr(record, "name", ""),
        getattr(record, "source", ""),
        Path(str(getattr(record, "source", "") or "")).stem,
        getattr(record, "algorithm_id", ""),
        *actions,
        *(_action_title(action) for action in actions),
        artifact.get("artifact_id", ""),
        artifact.get("name", ""),
        artifact.get("file_name", ""),
        artifact.get("display_title", ""),
        artifact.get("display_summary", ""),
    ]
    parts.extend(str(item) for item in list(getattr(record, "parent_ids", None) or []))
    for mapping in (parameters, lineage, artifact):
        for value in mapping.values():
            parts.append(_value_text(value))
    return _normalize_text(" ".join(part for part in parts if str(part or "").strip()))


def _value_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_value_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_value_text(item) for item in value)
    return str(value or "")


def _record_distance_matches(record: Any, target: float) -> bool:
    parameters = dict(getattr(record, "parameters", None) or {})
    lineage = _lineage(record)
    lineage_parameters = dict(lineage.get("parameters") or {}) if isinstance(lineage.get("parameters"), dict) else {}
    values = [
        parameters.get("distance"),
        parameters.get("DISTANCE"),
        lineage_parameters.get("distance"),
        lineage_parameters.get("DISTANCE"),
    ]
    for value in values:
        try:
            if value is not None and abs(float(value) - target) < 1e-6:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _distance_value(query: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(km|公里|千米|m|meter|meters|米)?", query)
    if not match:
        return None
    value = float(match.group(1))
    unit = str(match.group(2) or "").strip().lower()
    if unit in {"km", "公里", "千米"}:
        return value * 1000.0
    return value


def _strip_previous_hints(query: str) -> str:
    text = query
    for hint in _PREVIOUS_HINTS:
        text = text.replace(hint, "")
    return text or query


def _operation_from_text(query: str) -> str:
    for operation, hints in _OPERATION_HINTS.items():
        if any(_normalize_text(hint) in query for hint in hints):
            return operation
    return ""


def _looks_boundary_related(text: str) -> bool:
    return "boundary" in text or "边界" in text or "polygon" in text


def _record_matches_group(facts: _RecordFacts, group: str) -> bool:
    candidates = tuple(str(item).lower() for item in _ACTION_GROUPS.get(group, ()))
    for action in facts.actions:
        lowered = str(action or "").lower()
        if any(candidate in lowered for candidate in candidates):
            return True
    return False


def _is_final_record(record: Any) -> bool:
    facts = _record_facts(record)
    return facts.role == "final" or "export_result" in facts.actions


def _record_facts(record: Any) -> _RecordFacts:
    metadata = dict(getattr(record, "metadata", None) or {})
    artifact = dict(metadata.get("artifact") or {})
    lineage = _lineage(record)
    actions = [
        str(getattr(record, "algorithm_id", "") or ""),
        str(getattr(record, "source_action", "") or ""),
        str(metadata.get("source_action") or ""),
        str(artifact.get("algorithm_id") or ""),
        str(artifact.get("source_action") or ""),
        str(lineage.get("operation") or ""),
        str(lineage.get("source_action") or ""),
    ]
    role = str(artifact.get("role") or metadata.get("artifact_role") or getattr(record, "role", "") or "").strip().lower()
    source_step = metadata.get("source_step", artifact.get("source_step", lineage.get("source_step")))
    return _RecordFacts(
        actions=[action.strip() for action in dict.fromkeys(actions) if action.strip()],
        role=role,
        source_step=_int_or_none(source_step),
    )


def _candidate_for_record(record: Any, *, score: int) -> LayerReferenceCandidate:
    facts = _record_facts(record)
    return LayerReferenceCandidate(
        layer_id=str(getattr(record, "layer_id", "") or ""),
        name=str(getattr(record, "name", "") or ""),
        score=int(score or 0),
        role=facts.role,
        source_action=_source_action(facts),
        source_step=facts.source_step,
    )


def _source_action(facts: _RecordFacts) -> str:
    for action in facts.actions:
        if action and not action.startswith("native:"):
            return action
    return facts.actions[0] if facts.actions else ""


def _is_ambiguous(candidates: list[LayerReferenceCandidate]) -> bool:
    if len(candidates) < 2:
        return False
    top = candidates[0].score
    second = candidates[1].score
    return top - second <= 1


def _lineage(record: Any) -> dict[str, Any]:
    metadata = dict(getattr(record, "metadata", None) or {})
    artifact = dict(metadata.get("artifact") or {})
    lineage = dict(getattr(record, "lineage", None) or {})
    for candidate in (metadata.get("lineage"), artifact.get("lineage")):
        if not lineage and isinstance(candidate, dict):
            lineage = dict(candidate)
    return lineage


def _input_layer_ids(record: Any) -> list[str]:
    lineage = _lineage(record)
    metadata = dict(getattr(record, "metadata", None) or {})
    artifact = dict(metadata.get("artifact") or {})
    candidates = (
        list(getattr(record, "parent_ids", None) or [])
        or list(lineage.get("input_layer_ids") or [])
        or list(artifact.get("input_layer_ids") or [])
    )
    return [str(item).strip() for item in candidates if str(item or "").strip()]


def _source_step(record: Any) -> int:
    value = _record_facts(record).source_step
    return value if value is not None else 0


def _record_layer_id(record: Any | None) -> str | None:
    if record is None:
        return None
    return str(getattr(record, "layer_id", "") or "").strip() or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _action_title(action: str) -> str:
    try:
        from pineflow_agent.tools.contracts.tool_definitions import display_title_for_action

        return display_title_for_action(action)
    except Exception:
        return str(action or "")


def _normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", "", text)
    return text
