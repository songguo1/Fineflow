"""State tree for chainable intermediate GIS layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_agent.core.layer_reference_resolver import (
    ArtifactGraphResolver,
    LayerReferencePhraseParser,
    LayerReferenceQuery,
    LayerReferenceResolution,
)
from pineflow_agent.core.models import LayerKind


@dataclass
class LayerRecord:
    layer_id: str
    name: str
    kind: LayerKind
    source: str
    parent_ids: list[str] = field(default_factory=list)
    algorithm_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "name": self.name,
            "kind": self.kind,
            "source": self.source,
            "parent_ids": list(self.parent_ids),
            "algorithm_id": self.algorithm_id,
            "parameters": make_json_safe(self.parameters),
            "metadata": make_json_safe(self.metadata),
        }


class GISStateTree:
    """Tracks initial, temporary, and exported layers by stable ids."""

    _LATEST_REFS = {
        "latest",
        "latest_layer",
        "latest_result",
        "latest_output",
        "上一步结果",
        "上个结果",
        "最新结果",
        "最新输出",
    }
    _FINAL_REFS = {
        "final",
        "final_result",
        "final_output",
        "最终结果",
        "最终输出",
        "输出结果",
    }

    def __init__(self) -> None:
        self._layers: dict[str, LayerRecord] = {}
        self._aliases: dict[str, str] = {}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GISStateTree":
        tree = cls()
        for item in list((payload or {}).get("layers") or []):
            if not isinstance(item, dict):
                continue
            record = LayerRecord(
                layer_id=str(item.get("layer_id") or ""),
                name=str(item.get("name") or ""),
                kind=item.get("kind") or "unknown",
                source=str(item.get("source") or ""),
                parent_ids=list(item.get("parent_ids") or []),
                algorithm_id=str(item.get("algorithm_id") or ""),
                parameters=make_json_safe(dict(item.get("parameters") or {})),
                metadata=make_json_safe(dict(item.get("metadata") or {})),
            )
            if not record.layer_id:
                record.layer_id = cls._new_layer_id(record.name or record.source or "layer")
            tree._layers[record.layer_id] = record
        aliases = dict((payload or {}).get("aliases") or {})
        if aliases:
            tree._aliases = {str(key): str(value) for key, value in aliases.items()}
        for record in tree._layers.values():
            tree._register_record_aliases(record)
        return tree

    def add_layer(
        self,
        *,
        name: str,
        kind: LayerKind,
        source: str,
        parent_ids: list[str] | None = None,
        algorithm_id: str = "",
        parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        layer_id: str | None = None,
    ) -> LayerRecord:
        clean_name = str(name or "").strip() or self._derive_name(source, algorithm_id)
        record = LayerRecord(
            layer_id=layer_id or self._new_layer_id(clean_name),
            name=clean_name,
            kind=kind,
            source=str(source or ""),
            parent_ids=list(parent_ids or []),
            algorithm_id=str(algorithm_id or ""),
            parameters=make_json_safe(dict(parameters or {})),
            metadata=make_json_safe(dict(metadata or {})),
        )
        self._layers[record.layer_id] = record
        self._register_record_aliases(record)
        return record

    def resolve(self, layer_ref: str) -> LayerRecord:
        ref = str(layer_ref or "").strip()
        if not ref:
            raise KeyError("Layer reference is empty.")
        lowered = ref.lower()
        if lowered in self._LATEST_REFS:
            latest = self.latest_layer()
            if latest is not None:
                return latest
        if lowered in self._FINAL_REFS:
            final = self._latest_final_layer()
            if final is not None:
                return final
        layer_id = self._aliases.get(ref) or self._aliases.get(lowered) or ref
        if layer_id not in self._layers:
            resolution = self.resolve_reference_report(ref)
            if resolution.best_layer_id:
                layer_id = resolution.best_layer_id
        if layer_id not in self._layers:
            raise KeyError(f"Unknown layer reference: {ref}")
        return self._layers[layer_id]

    def resolve_reference_report(self, layer_ref: str | LayerReferenceQuery) -> LayerReferenceResolution:
        query = layer_ref if isinstance(layer_ref, LayerReferenceQuery) else LayerReferencePhraseParser().parse(str(layer_ref or ""))
        return ArtifactGraphResolver(list(self._layers.values())).resolve_with_report(query)

    def has_layer(self, layer_ref: str) -> bool:
        try:
            self.resolve(layer_ref)
            return True
        except KeyError:
            return False

    def set_alias(self, alias: str, target_ref: str) -> None:
        clean_alias = str(alias or "").strip()
        if not clean_alias:
            return
        target = self.resolve(target_ref)
        self._aliases[clean_alias] = target.layer_id
        self._aliases[clean_alias.lower()] = target.layer_id

    def latest_layer(self) -> LayerRecord | None:
        if not self._layers:
            return None
        return list(self._layers.values())[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "layers": [record.to_dict() for record in self._layers.values()],
            "aliases": dict(self._aliases),
        }

    @staticmethod
    def _derive_name(source: str, algorithm_id: str) -> str:
        if source:
            return Path(source).stem or "layer"
        if algorithm_id:
            return algorithm_id.replace(":", "_")
        return "layer"

    @staticmethod
    def _new_layer_id(name: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name).strip("_")
        safe = safe or "layer"
        return f"{safe}_{uuid4().hex[:8]}"

    def _register_record_aliases(self, record: LayerRecord) -> None:
        for alias in self._candidate_aliases(record):
            self._aliases.setdefault(alias, record.layer_id)
            self._aliases.setdefault(alias.lower(), record.layer_id)

    def _candidate_aliases(self, record: LayerRecord) -> list[str]:
        aliases: list[str] = [record.layer_id]
        if record.name:
            aliases.append(record.name)
        metadata = dict(record.metadata or {})
        artifact = dict(metadata.get("artifact") or {})
        for key in ("artifact_id", "name", "file_name"):
            value = str(artifact.get(key) or "").strip()
            if value:
                aliases.append(value)
        artifact_path = str(artifact.get("path") or "").strip()
        if artifact_path:
            stem = Path(artifact_path).stem.strip()
            if stem:
                aliases.append(stem)
        source_stem = Path(record.source).stem.strip() if str(record.source or "").strip() else ""
        if source_stem:
            aliases.append(source_stem)
        return list(dict.fromkeys(item for item in aliases if str(item or "").strip()))

    def _latest_final_layer(self) -> LayerRecord | None:
        for record in reversed(list(self._layers.values())):
            if self._is_final_record(record):
                return record
        return None

    @staticmethod
    def _is_final_record(record: LayerRecord) -> bool:
        metadata = dict(record.metadata or {})
        artifact = dict(metadata.get("artifact") or {})
        role = str(artifact.get("role") or metadata.get("artifact_role") or "").strip().lower()
        algorithm_id = str(record.algorithm_id or artifact.get("algorithm_id") or "").strip().lower()
        return role == "final" or algorithm_id == "export_result"
