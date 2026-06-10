"""Data source inspection helpers for QGIS toolbox inputs."""

from __future__ import annotations

import csv
from datetime import datetime
import io
from pathlib import Path
from typing import Any

from pineflow_runtime.errors import ToolValidationError


class QGISDataSourceInspector:
    """Inspect local data source paths before QGIS runtime execution."""

    @staticmethod
    def existing_path(input_path: str) -> str:
        path = Path(str(input_path or "").strip()).expanduser().resolve()
        if not path.exists():
            raise ToolValidationError(f"Input path does not exist: {path}")
        return str(path)

    @classmethod
    def inspect_csv(cls, input_path: str) -> dict[str, Any]:
        text, encoding = cls.read_text_with_fallback(input_path)
        with io.StringIO(text, newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(handle, dialect=dialect)
            fields = [str(field or "").strip() for field in list(reader.fieldnames or []) if str(field or "").strip()]
            if not fields:
                raise ToolValidationError(f"CSV has no header row: {input_path}")
            null_counts: dict[str, int] = {field: 0 for field in fields}
            samples: dict[str, list[str]] = {field: [] for field in fields}
            row_count = 0
            for row in reader:
                row_count += 1
                for field in fields:
                    value = str((row or {}).get(field) or "").strip()
                    if not value:
                        null_counts[field] += 1
                        continue
                    if len(samples[field]) < 5 and value not in samples[field]:
                        samples[field].append(value)
        return {
            "source_path": input_path,
            "fields": fields,
            "field_summaries": [
                {
                    "name": field,
                    "type": cls.infer_field_type(samples[field]),
                    "null_count": null_counts[field],
                    "sample_values": samples[field],
                }
                for field in fields
            ],
            "null_counts": null_counts,
            "sample_values": samples,
            "row_count": row_count,
            "geometry_type": "None",
            "crs": "",
            "provider": "csv",
            "encoding": encoding,
        }

    @staticmethod
    def read_text_with_fallback(input_path: str) -> tuple[str, str]:
        data = Path(input_path).read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "cp1252", "latin-1"):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace"), "utf-8-replace"

    @classmethod
    def csv_field_diagnostics(cls, fields: list[str]) -> dict[str, Any]:
        suspicious_fields = [field for field in fields if cls.looks_like_mojibake(field)]
        return {
            "suspected_encoding_issue": bool(suspicious_fields),
            "suspicious_fields": suspicious_fields,
        }

    @staticmethod
    def infer_field_type(values: list[Any]) -> str:
        non_empty = [str(value or "").strip() for value in list(values or []) if str(value or "").strip()]
        if not non_empty:
            return "string"
        if all(_looks_int(value) for value in non_empty):
            return "integer"
        if all(_looks_float(value) for value in non_empty):
            return "float"
        if all(_looks_iso_date(value) for value in non_empty):
            return "date"
        return "string"

    @staticmethod
    def looks_like_mojibake(value: str) -> bool:
        text = str(value or "")
        if not text:
            return False
        if "\ufffd" in text:
            return True
        if "?" in text and any(ord(char) > 127 for char in text):
            return True
        return text.count("锟") > 0


def _looks_int(value: str) -> bool:
    try:
        int(str(value).strip())
        return True
    except ValueError:
        return False


def _looks_float(value: str) -> bool:
    try:
        float(str(value).strip())
        return True
    except ValueError:
        return False


def _looks_iso_date(value: str) -> bool:
    text = str(value or "").strip()
    for parser in (datetime.fromisoformat,):
        try:
            parser(text)
            return True
        except ValueError:
            continue
    return False
