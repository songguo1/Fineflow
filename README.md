# PineFlow

[中文](README.zh-CN.md)

<p align="center">
  <img src="apps/desktop/src/assets/pineflow-wordmark.png" alt="PineFlow" width="360">
</p>

PineFlow is a tool-calling GIS agent for QGIS workflows. It turns natural-language GIS requests into validated QGIS Processing / PyQGIS operations through a ReAct-style observe-act loop.

PineFlow is currently a graduation-thesis prototype. It focuses on structured GIS processing workflows and does not aim to replace the full QGIS desktop experience, such as cartographic styling, interactive editing, map layout design, or manual visual inspection.

## Links

- Demo video: [Bilibili](https://www.bilibili.com/video/BV1N6Jg6xEYT)
- Chinese article: [WeChat Official Account](https://mp.weixin.qq.com/s/NMACoA4dCgp8wsIiV35ovQ)

## Features

- Natural-language GIS workflow execution
- ReAct-style observe-act loop with native LLM tool calling
- QGIS Processing / PyQGIS execution through an isolated runtime worker
- ToolKit-based capability disclosure to reduce context noise
- Skill-based GIS task guidance loaded on demand
- Rules gateway for semantic validation and GIS preflight checks
- Session state, run events, artifacts, outputs, and workspace snapshots
- FastAPI backend service
- Tauri v2 + React desktop application

## Repository Layout

```text
src/
  pineflow_agent/
    core/             Agent state, workspace models, messages, artifacts
    llm/              LLM clients, model adapters, prompt/context assembly
    orchestration/    ReAct loop, run execution, resume flow, result projection
    policies/         Output, CRS, and autonomy policies
    risks/            Risk diagnostics and risk conversion logic
    rules/            Semantic validation, preflight checks, resume rules
    tools/            Tool definitions, registry, ToolKits, QGIS tool wrappers

  pineflow_api/
    application/      Run, session, state-query, and QGIS runtime services
    contracts/        API contracts, run lifecycle, events, snapshots
    entrypoints/      FastAPI entrypoint and PyQGIS worker entrypoint
    persistence/      SQLite session store, event stream, run snapshots
    routing/          Slash commands, intent routing, session routing

  pineflow_runtime/
    runtime.py        Concrete PyQGIS execution logic
    errors.py         Runtime error definitions

apps/
  desktop/
    src/              React frontend source
    src-tauri/        Tauri v2 native desktop project
    package.json      Desktop dependencies and scripts
    vite.config.js    Vite configuration

resources/
  skills/             GIS domain guidance loaded by the agent
  toolkits/           ToolKit capability definitions

.pineflow/            Local runtime state and default session outputs, ignored by Git
```

## Architecture

```text
Desktop UI
  |
FastAPI Backend
  |
ReAct GIS Agent
  |
QGIS / PyQGIS Runtime
```

The desktop app does not execute GIS operations directly. It creates runs through the backend API, polls run events, and renders session state, workflow steps, outputs, and analysis reports.

The backend manages sessions, runs, event streams, state snapshots, slash commands, intent routing, and execution orchestration.

The agent converts a user request into a sequence of validated GIS tool calls:

```text
Read workspace state
  |
Build ReAct prompt
  |
Ask the LLM for one native tool call
  |
Validate through the rules gateway
  |
Execute the tool
  |
Record observation
  |
Continue, ask for confirmation, or return final answer
```

The runtime layer performs the actual QGIS work, such as buffering, clipping, geometry repair, raster calculation, reprojection, and exporting results.

## ToolKits

PineFlow groups tools by ToolKit. Only the currently relevant ToolKits are disclosed to the model during a run.

| ToolKit | Main capabilities |
| --- | --- |
| `data_io` | Load vector/raster/CSV data, convert CSV to points, summarize layers, export results |
| `vector_transform` | Reproject, fix geometries, centroid, point on surface, multipart to singlepart, simplify geometry |
| `vector_analysis` | Buffer, dissolve, merge layers, attribute filter, spatial join, nearest join, count points in polygon, field calculation |
| `vector_overlay` | Clip, intersect, difference, union, symmetrical difference, extract by location |
| `raster` | Raster reprojection, mask/extent clipping, raster calculator, zonal statistics, raster sampling, vector rasterization, polygonization |
| `qgis_generic` | Discover QGIS algorithms, inspect algorithm help, and use a controlled generic algorithm entry when needed |

## Skills

Skills are Markdown guidance files under `resources/skills/`. They are not executors and do not replace rule validation. They provide GIS task knowledge to the model when useful, such as CRS handling for meter-based buffers, CSV longitude/latitude detection, boundary filtering risks, and spatial join considerations.

## Requirements

- Python 3.10+
- Node.js 18+
- Rust toolchain
- QGIS LTR
- An OpenAI-compatible LLM provider, such as DeepSeek, OpenAI-compatible APIs, Qwen, or GLM

Real GIS execution requires a local QGIS installation. Basic code checks and some frontend development do not require QGIS to be running.

## Configuration

PineFlow reads configuration from process environment variables and from the desktop settings panel. The project does not require a local environment file.

At minimum, configure an LLM provider before starting the backend:

```powershell
$env:PINEFLOW_LLM_PROVIDER="deepseek"
$env:PINEFLOW_LLM_BASE_URL="https://api.deepseek.com"
$env:PINEFLOW_LLM_MODEL="deepseek-v4-pro"
$env:DEEPSEEK_API_KEY="your_api_key"
```

For real QGIS processing, configure the local QGIS runtime as well:

```powershell
$env:QGIS_LAUNCHER="D:\software\QGIS\bin\python-qgis-ltr.bat"
$env:QGIS_PREFIX_PATH="D:\software\QGIS\apps\qgis-ltr"
```

These values can also be filled in through the desktop settings UI.

## QGIS Configuration

PineFlow separates the backend/agent Python environment from the PyQGIS runtime. The FastAPI service and agent can run in a normal Python environment. Concrete GIS operations are delegated to the local QGIS installation when needed.

Two QGIS paths are important:

- `QGIS Launcher`: the QGIS Python launcher, usually a `.bat` file or executable. PineFlow uses it to start a runtime worker inside QGIS's Python environment, so PyQGIS imports and Processing providers are available.
- `QGIS Prefix Path`: the QGIS application prefix directory. QGIS uses this path to locate libraries, plugins, resources, and Processing algorithms.

Common Windows QGIS LTR examples:

```text
QGIS Launcher:
D:\software\QGIS\bin\python-qgis-ltr.bat
C:\Program Files\QGIS 3.34.*/bin/python-qgis-ltr.bat
C:\Program Files\QGIS 3.40.*/bin/python-qgis.bat

QGIS Prefix Path:
D:\software\QGIS\apps\qgis-ltr
C:\Program Files\QGIS 3.34.*/apps/qgis-ltr
C:\Program Files\QGIS 3.40.*/apps/qgis
```

Launcher and prefix path are not input data directories. They describe how PineFlow finds and starts the local QGIS runtime.

If QGIS is not configured correctly, the API and desktop UI may still start, but real GIS operations such as buffer, clip, reprojection, raster processing, and export may fail.

## Quick Start

Install the Python package from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e .
```

Start the backend API in terminal 1:

```powershell
py -m pineflow_api --host 127.0.0.1 --port 8765
```

The backend listens on:

```text
http://127.0.0.1:8765
```

Main API routes are under:

```text
/qgis/*
```

Start the desktop app in terminal 2:

```powershell
cd apps/desktop
npm install
npm run dev
```

Browser-only frontend development:

```powershell
npm run dev:web
```

Build the web bundle:

```powershell
npm run build:web
```

Build the native desktop app:

```powershell
npm run build
```

## Local Runtime State And Outputs

PineFlow stores local runtime state under `.pineflow/`. This directory is not source code and should not be committed to Git.

Default session outputs are stored under:

```text
.pineflow/sessions/{session_id}/outputs/
```

The repository also ignores local GIS data, generated outputs, caches, build artifacts, assistant metadata, and test-only files.

## Development Status

PineFlow is still experimental. Its current focus is a reliable tool-calling harness around QGIS Processing / PyQGIS workflows, including validation, workspace state, event traces, and reproducible outputs.

## License

MIT License. See [LICENSE](LICENSE).
