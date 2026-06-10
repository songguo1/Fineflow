"""Layer registration helper for QGIS toolbox operations."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.artifacts import ArtifactRole
from pineflow_agent.core.models import LayerKind, Observation
from pineflow_agent.core.state_tree import GISStateTree, LayerRecord
from pineflow_agent.tools.qgis.artifact_recorder import QGISArtifactRecorder


class QGISLayerRegistrar:
    """Register state-tree layers and their artifact records in one place."""

    def __init__(self, state: GISStateTree, artifact_recorder: QGISArtifactRecorder) -> None:
        self.state = state
        self.artifact_recorder = artifact_recorder

    def register(
        self,
        *,
        name: str,
        kind: LayerKind,
        source: str,
        role: ArtifactRole,
        parent_ids: list[str] | None = None,
        algorithm_id: str = "",
        source_action: str = "",
        parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LayerRecord:
        next_metadata = dict(metadata or {})
        if source_action:
            next_metadata["source_action"] = source_action
        record = self.state.add_layer(
            name=name,
            kind=kind,
            source=source,
            parent_ids=parent_ids,
            algorithm_id=algorithm_id,
            parameters=parameters,
            metadata=next_metadata,
        )
        artifact = self.artifact_recorder.record(record, role=role)
        if artifact is not None:
            artifact_payload = artifact.output_dict()
            next_metadata = dict(record.metadata or {})
            next_metadata["artifact"] = artifact_payload
            next_metadata["artifact_id"] = artifact.artifact_id
            next_metadata["artifact_role"] = artifact.role
            next_metadata["artifact_path"] = artifact.path
            next_metadata["artifact_reusable"] = artifact.reusable
            next_metadata["artifact_materialized"] = artifact.materialized
            next_metadata["input_artifact_ids"] = list(artifact.input_artifact_ids)
            next_metadata["input_artifacts"] = list(artifact.input_artifacts)
            next_metadata["lineage"] = dict(artifact.lineage)
            record.metadata = next_metadata
        return record

    @staticmethod
    def success_observation(
        record: LayerRecord,
        *,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> Observation:
        return Observation(
            status="success",
            message=message,
            output_layer_id=record.layer_id,
            output_path=record.source,
            data=dict(data or {}),
        )
