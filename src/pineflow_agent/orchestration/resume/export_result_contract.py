"""Structured resume helpers for export_result clarifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

EXPORT_RESULT_FORMATS = (".geojson", ".gpkg", ".shp")
DEFAULT_EXPORT_NAME = "export_result"


def export_result_slot_patch_schema() -> dict[str, dict[str, Any]]:
    return {
        "output_dir": {
            "required": True,
            "type": "string",
            "format": "directory",
            "description": "Directory where the export should be written.",
        },
        "output_format": {
            "required": True,
            "type": "string",
            "enum": list(EXPORT_RESULT_FORMATS),
            "description": "Export file format.",
        },
        "output_name": {
            "required": False,
            "type": "string",
            "description": "Export file name without extension.",
        },
    }


def export_result_missing_slots() -> list[str]:
    return ["output_dir", "output_format"]


def export_result_question(default_question: str = "") -> str:
    del default_question
    return "请指定导出目录、格式和文件名后继续。"


def compose_export_result_path(action_input: dict[str, Any]) -> str:
    direct_path = str(action_input.get("output_path") or "").strip()
    if direct_path:
        return direct_path if direct_path.upper() != "TEMPORARY_OUTPUT" else ""

    output_dir = str(action_input.get("output_dir") or "").strip()
    output_format = _normalize_output_format(action_input.get("output_format"))
    if not output_dir or not output_format:
        return ""

    output_name = str(action_input.get("output_name") or "").strip() or DEFAULT_EXPORT_NAME
    stem = Path(output_name).stem or DEFAULT_EXPORT_NAME
    return str((Path(output_dir).expanduser() / stem).with_suffix(output_format))


def export_result_patch_from_values(values: dict[str, Any]) -> dict[str, Any]:
    patch = dict(values or {})
    output_path = compose_export_result_path(patch)
    if output_path:
        patch["output_path"] = output_path
    else:
        patch.pop("output_path", None)
    return patch


def _normalize_output_format(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if not text.startswith("."):
        text = f".{text}"
    return text if text in EXPORT_RESULT_FORMATS else ""
