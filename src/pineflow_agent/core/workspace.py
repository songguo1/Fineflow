"""Workspace path abstraction for PineFlow GIS sessions.

OpenClaw-aligned layout:
    <root>/
      project.md           Project-level GIS workspace config
      data/                Input data (persistent)
      resources/skills/    GIS skills
      resources/toolkits/  ToolKit YAML definitions
      docs/                Documentation
      .pineflow/           PineFlow runtime root
        pineflow_state.db  SQLite/WAL live session state
        sessions/          Per-session files for outputs, memory, artifacts, and legacy imports
          {session_id}/
            outputs/       Exported results
            temp/          Intermediate QGIS outputs
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class WorkspaceContext:
    """Project/session filesystem boundary used by agents and API storage."""

    root: str | Path = "."
    session_id: str = "default"
    data_root: str | Path | None = None
    layer_metadata_root: str | Path | None = None
    reports_root: str | Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root or ".").resolve())
        object.__setattr__(self, "session_id", safe_workspace_name(self.session_id or "default"))
        for attr in ("data_root", "layer_metadata_root", "reports_root"):
            value = getattr(self, attr)
            if value is not None:
                object.__setattr__(self, attr, Path(value).expanduser().resolve())

    def with_session(self, session_id: str) -> "WorkspaceContext":
        return WorkspaceContext(
            root=self.root,
            session_id=session_id or self.session_id,
            data_root=self.data_root,
            layer_metadata_root=self.layer_metadata_root,
            reports_root=self.reports_root,
        )

    # ── project-level paths ──────────────────────────────────────────────

    @property
    def pineflow_dir(self) -> Path:
        return self.root / ".pineflow"

    @property
    def project_file(self) -> Path:
        return self.root / "project.md"

    @property
    def data_dir(self) -> Path:
        return Path(self.data_root or self.root / "data")

    @property
    def skills_dir(self) -> Path:
        return self.root / "resources" / "skills"

    @property
    def toolkits_dir(self) -> Path:
        return self.root / "resources" / "toolkits"

    def layer_metadata_dir(self) -> Path:
        return Path(self.layer_metadata_root or self.root / "layer_metadata")

    @property
    def reports_dir(self) -> Path:
        return Path(self.reports_root or self.root / "reports")

    # ── session-level paths ──────────────────────────────────────────────

    @property
    def sessions_root_dir(self) -> Path:
        return self.pineflow_dir / "sessions"

    @property
    def session_dir(self) -> Path:
        return self.sessions_root_dir / self.session_id

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "manifest.json"

    @property
    def state_tree_path(self) -> Path:
        return self.session_dir / "state_tree.json"

    @property
    def steps_path(self) -> Path:
        return self.session_dir / "steps.jsonl"

    @property
    def pending_path(self) -> Path:
        return self.session_dir / "pending.json"

    @property
    def layers_dir(self) -> Path:
        return self.session_dir / "layers"

    @property
    def event_log_path(self) -> Path:
        return self.session_dir / "events.jsonl"

    @property
    def artifacts_index_path(self) -> Path:
        return self.session_dir / "artifacts.json"

    @property
    def session_memory_path(self) -> Path:
        return self.session_dir / "session_memory.md"

    @property
    def outputs_dir(self) -> Path:
        return self.session_dir / "outputs"

    @property
    def temp_dir(self) -> Path:
        return self.session_dir / "temp"

    # ── directory helpers ────────────────────────────────────────────────

    def ensure_project_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.sessions_root_dir,
            self.layer_metadata_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def ensure_session_dirs(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.layers_dir.mkdir(parents=True, exist_ok=True)

    def output_path(self, file_name: str) -> str:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        return str((self.outputs_dir / file_name).resolve())

    def temp_output_path(self, file_name: str) -> str:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return str((self.temp_dir / file_name).resolve())

    def catalog_path(self, artifact_id: str) -> str:
        """Return a stable output path for a cataloged artifact.

        Unlike temp_output_path, this places the file in the session
        outputs directory so it can be referenced across sessions.
        """
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        safe = safe_workspace_name(artifact_id)
        return str((self.outputs_dir / f"{safe}.gpkg").resolve())


def safe_workspace_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or ""))
    safe = safe.strip("_-")
    return safe or uuid4().hex[:8]
