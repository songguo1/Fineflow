"""Configuration helpers for the PineFlow API."""

from __future__ import annotations

import os

DEFAULT_QGIS_LAUNCHER = r"D:\software\QGIS\bin\python-qgis-ltr.bat"
DEFAULT_QGIS_PREFIX_PATH = r"D:\software\QGIS\apps\qgis-ltr"


def first_env(names: list[str], default: str = "") -> str:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return default


def default_llm_provider() -> str:
    return first_env(["PINEFLOW_LLM_PROVIDER", "QGIS_AGENT_LLM_PROVIDER", "GIS_REACT_PROVIDER"], "deepseek")


def default_llm_base_url() -> str:
    return first_env(["PINEFLOW_LLM_BASE_URL", "QGIS_AGENT_LLM_BASE_URL", "GIS_REACT_BASE_URL"], "https://api.deepseek.com")


def default_llm_model() -> str:
    return first_env(["PINEFLOW_LLM_MODEL", "QGIS_AGENT_LLM_MODEL", "GIS_REACT_MODEL"], "deepseek-v4-pro")


def default_llm_api_key() -> str:
    return first_env(["DEEPSEEK_API_KEY", "PINEFLOW_LLM_API_KEY", "QGIS_AGENT_LLM_API_KEY", "GIS_REACT_API_KEY"])
