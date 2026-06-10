"""Command-line entrypoint for the standalone QGIS ReAct agent."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pineflow_agent.llm.llm import OpenAICompatibleLLM
from pineflow_agent.orchestration.agent.react_loop import ReActGISAgent
from pineflow_agent.tools.qgis.toolbox import QGISToolbox


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the standalone QGIS ReAct agent.")
    parser.add_argument("--request", required=True, help="Natural language GIS request.")
    parser.add_argument(
        "--provider",
        dest="provider",
        choices=["openai-compatible"],
        default="openai-compatible",
        help="LLM provider backend.",
    )
    parser.add_argument("--api-key", default=os.environ.get("GIS_REACT_API_KEY", ""))
    parser.add_argument("--base-url", default=os.environ.get("GIS_REACT_BASE_URL", ""))
    parser.add_argument("--model", default=os.environ.get("GIS_REACT_MODEL", ""))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--session-id", default="", help="Optional session id to embed in the result payload.")
    parser.add_argument(
        "--auto-repair",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue by repairing from tool errors when possible.",
    )
    parser.add_argument(
        "--vector",
        action="append",
        default=[],
        metavar="ALIAS=PATH",
        help="Preload a vector layer into the state tree. May be repeated.",
    )
    parser.add_argument(
        "--raster",
        action="append",
        default=[],
        metavar="ALIAS=PATH",
        help="Preload a raster layer into the state tree. May be repeated.",
    )
    return parser


def build_llm(args: argparse.Namespace) -> Any:
    return OpenAICompatibleLLM(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
    )


def parse_alias_path(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if "=" not in text:
        raise ValueError(f"Expected ALIAS=PATH, got: {value}")
    alias, path = text.split("=", 1)
    alias = alias.strip()
    path = path.strip().strip('"')
    if not alias:
        raise ValueError(f"Layer alias cannot be empty: {value}")
    if not path:
        raise ValueError(f"Layer path cannot be empty: {value}")
    return alias, str(Path(path).expanduser().resolve())


def preload_layers(toolbox: QGISToolbox, *, vectors: list[str], rasters: list[str]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in vectors:
        alias, path = parse_alias_path(item)
        observation = toolbox.load_vector(path, name=alias)
        observations.append(observation.to_dict())
        if not observation.is_success:
            raise RuntimeError(f"Failed to preload vector {alias}: {observation.message}")
    for item in rasters:
        alias, path = parse_alias_path(item)
        observation = toolbox.load_raster(path, name=alias)
        observations.append(observation.to_dict())
        if not observation.is_success:
            raise RuntimeError(f"Failed to preload raster {alias}: {observation.message}")
    return observations


def main() -> None:
    args = build_parser().parse_args()
    llm = build_llm(args)
    toolbox = QGISToolbox()
    preload_observations = preload_layers(toolbox, vectors=args.vector, rasters=args.raster)
    agent = ReActGISAgent(llm=llm, toolbox=toolbox, auto_repair=args.auto_repair)
    result = agent.run(args.request, session_id=args.session_id)
    payload = result.to_dict()
    payload["preload_observations"] = preload_observations
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
