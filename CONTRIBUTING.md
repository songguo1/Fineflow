# Contributing

## Scope

Keep changes focused. PineFlow has three main layers:

- `src/pineflow_agent`: ReAct loop, LLM adapters, rules, tools, and QGIS toolbox.
- `src/pineflow_api`: FastAPI service, routing, run lifecycle, and persistence.
- `apps/desktop`: Tauri v2 + React desktop frontend.

Runtime state, local GIS data, generated outputs, and scratch documents should
not be committed.

## Development

Install Python dependencies:

```powershell
py -m pip install -e ".[dev]"
```

Install desktop dependencies:

```powershell
cd apps/desktop
npm install
```

## Checks

Run Python compile checks:

```powershell
py -m compileall src/pineflow_agent src/pineflow_api src/pineflow_runtime
```

Build the web frontend:

```powershell
cd apps/desktop
npm run build:web
```

## Pull Requests

- Keep unrelated refactors out of feature or bug-fix PRs.
- Add or update tests when behavior changes.
- Do not commit `.env`, `.pineflow`, `output`, `data`, build artifacts, or logs.
- Keep QGIS execution logic in `src/pineflow_runtime` and QGIS tool mapping in
  `src/pineflow_agent/tools/qgis`.
