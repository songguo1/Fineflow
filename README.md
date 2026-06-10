# PineFlow

PineFlow is a GIS automation agent platform for QGIS workflows. It combines a
ReAct-first Python agent, a FastAPI service, a PyQGIS runtime bridge, and a
Tauri + React desktop application.

The project is organized as a mixed Python and desktop app repository:

```text
src/                 Python packages
apps/desktop/        Tauri v2 + React desktop client
resources/           Agent skills and toolkit definitions
data/                Local GIS data, ignored by Git
output/              Local GIS outputs, ignored by Git
docs/                Local project notes, ignored by Git in this repository
```

## Requirements

- Python 3.10+
- Node.js 18+
- Rust toolchain, for Tauri desktop builds
- QGIS LTR, for real PyQGIS execution

The Python tests use fake toolboxes and do not require QGIS.

## Python Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set the model and QGIS paths for local runs.

## Run The API

```powershell
py -m pineflow_api --host 127.0.0.1 --port 8765
```

## Run The Desktop App

```powershell
cd apps/desktop
npm install
npm run dev
```

For browser-only frontend development:

```powershell
cd apps/desktop
npm run dev:web
```

## Build

```powershell
cd apps/desktop
npm run build:web
```

For native desktop packaging:

```powershell
cd apps/desktop
npm run build
```

## Repository Policy

Git tracks source code, runtime resource definitions, desktop app sources, and
minimal project metadata. Local tests, GIS datasets, generated outputs, model
keys, runtime SQLite state, scratch notes, and build artifacts are intentionally
ignored.
