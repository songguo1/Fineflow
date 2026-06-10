"""OpenClaw-style ToolKit disclosure for PineFlow tools.

ToolKits are defined as YAML files in the resources/toolkits directory.
The Python _default_toolkits() is kept as a fallback when YAML files are unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pineflow_agent.core.models import Observation, ReActStep
from pineflow_agent.tools.registry.tool_registry import RegisteredTool, ToolRegistry


@dataclass(frozen=True)
class ToolDisclosureOptions:
    """Configuration for ToolKit-first tool disclosure."""

    profile: str = "vector_raster_basic"
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolKitDefinition:
    name: str
    title: str
    description: str
    tools: tuple[str, ...]
    tags: tuple[str, ...] = ()
    profile: str = "vector_raster_basic"
    default_active: bool = False

    def to_prompt_dict(self, *, registry: ToolRegistry, include_run_algorithm: bool = False) -> dict[str, Any]:
        registered = registry.registered_tools()
        tools = [
            name
            for name in self.tools
            if name in registered and (include_run_algorithm or name != "run_algorithm")
        ]
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "tools": tools,
            "tags": list(self.tags),
        }


class ToolKitRegistry:
    """Registry of coarse-grained capability packs.

    Loads ToolKit definitions from resources/toolkits/*.yaml files when available,
    falling back to Python-defined _default_toolkits().
    """

    def __init__(self, toolkits: dict[str, ToolKitDefinition] | None = None) -> None:
        if toolkits is not None:
            self._toolkits = dict(toolkits)
        else:
            yaml_toolkits = _load_toolkits_from_yaml()
            self._toolkits = yaml_toolkits if yaml_toolkits else _default_toolkits()

    def get(self, name: str) -> ToolKitDefinition | None:
        return self._toolkits.get(str(name or "").strip())

    def names(self) -> tuple[str, ...]:
        return tuple(self._toolkits)

    def catalog(self, *, registry: ToolRegistry, include_run_algorithm: bool = False) -> list[dict[str, Any]]:
        return [
            toolkit.to_prompt_dict(registry=registry, include_run_algorithm=include_run_algorithm)
            for toolkit in self._toolkits.values()
        ]

    def expand(self, names: list[str] | tuple[str, ...], *, include_run_algorithm: bool = False) -> tuple[str, ...]:
        expanded: list[str] = []
        for name in names:
            toolkit = self.get(name)
            if toolkit is None:
                continue
            expanded.extend(
                tool
                for tool in toolkit.tools
                if include_run_algorithm or tool != "run_algorithm"
            )
        return tuple(_dedupe(expanded))


def _toolkits_yaml_root() -> Path | None:
    path = Path(__file__).resolve()
    for parent in path.parents:
        candidate = parent / "resources" / "toolkits"
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return None


def _load_toolkits_from_yaml() -> dict[str, ToolKitDefinition] | None:
    yaml_root = _toolkits_yaml_root()
    if yaml_root is None:
        return None
    yaml_files = sorted(yaml_root.glob("*.yaml"))
    if not yaml_files:
        return None
    toolkits: dict[str, ToolKitDefinition] = {}
    for yaml_path in yaml_files:
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        name = str(data.get("name") or yaml_path.stem)
        if not name:
            continue
        toolkits[name] = ToolKitDefinition(
            name=name,
            title=str(data.get("title") or name.replace("_", " ").title()),
            description=str(data.get("description") or ""),
            tools=tuple(data.get("tools") or ()),
            tags=tuple(data.get("tags") or ()),
            profile=str(data.get("profile") or "vector_raster_basic"),
            default_active=bool(data.get("default_active", False)),
        )
    return toolkits if toolkits else None


def _default_active_toolkits() -> list[str]:
    yaml_toolkits = _load_toolkits_from_yaml()
    if yaml_toolkits:
        return [name for name, tk in yaml_toolkits.items() if tk.default_active]
    return ["data_io"]


@dataclass
class ToolDisclosureController:
    """Owns per-run ToolKit visibility state."""

    options: ToolDisclosureOptions = field(default_factory=ToolDisclosureOptions)
    toolkit_registry: ToolKitRegistry = field(default_factory=ToolKitRegistry)
    active_toolkits: list[str] = field(default_factory=_default_active_toolkits)
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_steps(
        cls,
        steps: list[ReActStep],
        *,
        options: ToolDisclosureOptions,
        toolkit_registry: ToolKitRegistry | None = None,
    ) -> "ToolDisclosureController":
        controller = cls(options=options, toolkit_registry=toolkit_registry or ToolKitRegistry())
        for step in list(steps or []):
            if step.action != "select_toolkit" or not step.observation.is_success:
                continue
            data = dict(step.observation.data or {})
            active = [str(name) for name in list(data.get("active_toolkits") or []) if str(name)]
            if active:
                controller.active_toolkits = _dedupe(active)
            controller.history.append(
                {
                    "toolkits": list(data.get("selected_toolkits") or []),
                    "reason": str(data.get("reason") or ""),
                    "step": step.index,
                }
            )
        return controller

    def visible_tools(
        self,
        registry: ToolRegistry,
        *,
        allow: tuple[str, ...] = (),
        deny: tuple[str, ...] = (),
    ) -> dict[str, RegisteredTool]:
        registered = registry.registered_tools()
        profile = str(self.options.profile or "vector_raster_basic").strip() or "vector_raster_basic"
        allow_set = set(_normalize_names(tuple(self.options.allow) + tuple(allow)))
        deny_set = set(_normalize_names(tuple(self.options.deny) + tuple(deny)))
        include_run_algorithm = profile == "debug" or "run_algorithm" in allow_set
        expanded = self.toolkit_registry.expand(
            tuple(self.active_toolkits),
            include_run_algorithm=include_run_algorithm,
        )
        names = _dedupe(KERNEL_TOOLS + expanded + tuple(allow_set))
        if not include_run_algorithm:
            deny_set.add("run_algorithm")
        visible = [
            name
            for name in names
            if name in registered and (name in ALWAYS_VISIBLE_TOOLS or name not in deny_set)
        ]
        return {name: registered[name] for name in visible}

    def select_toolkits(self, action_input: dict[str, Any]) -> Observation:
        requested = action_input.get("toolkits")
        if isinstance(requested, str):
            requested_names = [requested]
        else:
            requested_names = [str(name) for name in list(requested or []) if str(name).strip()]
        requested_names = _dedupe(requested_names)
        invalid = [name for name in requested_names if self.toolkit_registry.get(name) is None]
        if invalid:
            return Observation(
                status="error",
                message=f"Unknown ToolKit(s): {', '.join(invalid)}.",
                data={
                    "requested_toolkits": requested_names,
                    "invalid_toolkits": invalid,
                    "available_toolkits": list(self.toolkit_registry.names()),
                },
            )
        if not requested_names:
            return Observation(
                status="error",
                message="select_toolkit requires at least one toolkit name.",
                data={"available_toolkits": list(self.toolkit_registry.names())},
            )
        self.active_toolkits = _dedupe(self.active_toolkits + requested_names)
        reason = str(action_input.get("reason") or "")
        item = {"toolkits": requested_names, "reason": reason}
        self.history.append(item)
        return Observation(
            status="success",
            message=f"Loaded ToolKit(s): {', '.join(requested_names)}.",
            data={
                "selected_toolkits": requested_names,
                "active_toolkits": list(self.active_toolkits),
                "reason": reason,
            },
        )

    def inspect_workspace(self, state_tree: dict[str, Any], action_input: dict[str, Any], registry: ToolRegistry) -> Observation:
        query_type = _workspace_query_type(action_input)
        context = dict(action_input.get("__context") or {}) if isinstance(action_input.get("__context"), dict) else {}
        layers = []
        for layer in list((state_tree or {}).get("layers") or []):
            if not isinstance(layer, dict):
                continue
            metadata = dict(layer.get("metadata") or {})
            layers.append(
                {
                    "layer_id": layer.get("layer_id"),
                    "name": layer.get("name"),
                    "kind": layer.get("kind"),
                    "crs": metadata.get("crs"),
                    "geometry_type": metadata.get("geometry_type"),
                    "feature_count": metadata.get("feature_count", metadata.get("row_count")),
                    "field_count": len(list(metadata.get("fields") or [])),
                    "fields": list(metadata.get("fields") or []),
                    "source": layer.get("source"),
                }
            )
        fields = [
            {"layer_id": layer.get("layer_id"), "name": layer.get("name"), "fields": list(layer.get("fields") or [])}
            for layer in layers
        ]
        data = {
            "query": str(action_input.get("query") or ""),
            "query_type": query_type,
            "layers": layers,
            "fields": fields,
            "outputs": list(context.get("outputs") or []),
            "risks": list(context.get("risks") or []),
            "memory": dict(context.get("memory") or {}),
            "active_run": dict(context.get("active_run") or {}),
            "active_toolkits": list(self.active_toolkits),
            "available_toolkits": self.toolkit_registry.catalog(
                registry=registry,
                include_run_algorithm=self.options.profile == "debug",
            ),
        }
        if query_type == "overview":
            selected = {key: data[key] for key in ("query", "query_type", "layers", "active_toolkits", "available_toolkits")}
        elif query_type == "toolkits":
            selected = {key: data[key] for key in ("query", "query_type", "active_toolkits", "available_toolkits")}
        else:
            selected = {key: data[key] for key in ("query", "query_type", query_type) if key in data}
        return Observation(
            status="success",
            message=f"Workspace inspected: {query_type}.",
            data=selected,
        )

    def prompt_catalog(self, registry: ToolRegistry) -> dict[str, Any]:
        return {
            "active_toolkits": list(self.active_toolkits),
            "available_toolkits": self.toolkit_registry.catalog(
                registry=registry,
                include_run_algorithm=self.options.profile == "debug",
            ),
            "history": list(self.history[-5:]),
        }


KERNEL_TOOLS = (
    "final_answer",
    "select_toolkit",
    "inspect_workspace",
    "suggest_skill",
    "load_skill",
    "proactive_clarification",
    "discover_algorithms",
    "algorithm_help",
)

ALWAYS_VISIBLE_TOOLS = (
    "final_answer",
    "select_toolkit",
    "inspect_workspace",
    "suggest_skill",
    "load_skill",
    "proactive_clarification",
)


def _workspace_query_type(action_input: dict[str, Any]) -> str:
    value = str(action_input.get("query_type") or "").strip().lower()
    if value in {"overview", "layers", "fields", "outputs", "risks", "memory", "active_run", "toolkits"}:
        return value
    return "overview"


def _default_toolkits() -> dict[str, ToolKitDefinition]:
    return {
        "data_io": ToolKitDefinition(
            name="data_io",
            title="Data IO",
            description="Load vector/raster/table data, create points from CSV, and export results.",
            tools=("load_vector", "load_raster", "load_csv", "summarize_layer", "csv_to_points", "export_result"),
            tags=("load", "csv", "export", "data", "summary"),
            default_active=True,
        ),
        "vector_transform": ToolKitDefinition(
            name="vector_transform",
            title="Vector transform and repair",
            description="Reproject, repair, simplify, and derive vector geometries.",
            tools=(
                "reproject_layer",
                "fix_geometries",
                "centroid_layer",
                "point_on_surface",
                "multipart_to_singlepart",
                "simplify_geometry",
            ),
            tags=("crs", "reproject", "repair", "geometry"),
        ),
        "vector_analysis": ToolKitDefinition(
            name="vector_analysis",
            title="Vector analysis",
            description="Buffer, dissolve, merge, join, count, and calculate vector attributes.",
            tools=(
                "buffer_layer",
                "dissolve_layer",
                "merge_layers",
                "extract_by_attribute",
                "keep_fields",
                "select_by_expression",
                "join_by_location",
                "join_by_nearest",
                "count_points_in_polygon",
                "field_calculator",
            ),
            tags=("buffer", "join", "attribute", "count"),
        ),
        "attribute_data": ToolKitDefinition(
            name="attribute_data",
            title="Attribute and data cleaning",
            description="Inspect fields, filter attributes, calculate fields, and tidy attribute tables.",
            tools=(
                "inspect_fields",
                "extract_by_attribute",
                "select_by_expression",
                "keep_fields",
                "rename_field",
                "field_calculator",
            ),
            tags=("attribute", "fields", "filter", "cleaning"),
        ),
        "vector_overlay": ToolKitDefinition(
            name="vector_overlay",
            title="Vector overlay and spatial filtering",
            description="Clip, intersect, union, difference, and extract features by location.",
            tools=(
                "clip_layer",
                "intersect_layer",
                "difference_layer",
                "union_layer",
                "symmetrical_difference",
                "extract_by_location",
            ),
            tags=("clip", "intersect", "within", "overlay"),
        ),
        "raster": ToolKitDefinition(
            name="raster",
            title="Raster analysis",
            description="Reproject, clip, calculate, sample, rasterize, polygonize, and run zonal statistics.",
            tools=(
                "reproject_raster",
                "clip_raster_by_mask",
                "clip_raster_by_extent",
                "raster_calculator",
                "zonal_statistics",
                "raster_sampling",
                "rasterize_vector",
                "polygonize_raster",
            ),
            tags=("raster", "tif", "zonal", "sample"),
        ),
        "qgis_generic": ToolKitDefinition(
            name="qgis_generic",
            title="Generic QGIS Processing",
            description="Search, inspect, and run uncommon QGIS Processing algorithms.",
            tools=("discover_algorithms", "algorithm_help", "run_algorithm"),
            tags=("processing", "algorithm", "debug"),
        ),
    }


def _normalize_names(values: tuple[str, ...]) -> list[str]:
    return _dedupe([str(value or "").strip() for value in values if str(value or "").strip()])


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result
