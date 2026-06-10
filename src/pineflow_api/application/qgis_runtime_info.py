"""QGIS runtime inspection helpers for health and toolbox metadata endpoints."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from pineflow_agent.core.json_safety import make_json_safe
from pineflow_runtime.runtime import QGISRuntime

from pineflow_api.application.qgis_launcher import launcher_command


class QGISRuntimeInfoService:
    """Reads QGIS availability and algorithm metadata without owning run execution."""

    def health(self, *, qgis: dict[str, Any] | None = None, deep: bool = False) -> dict[str, Any]:
        qgis_config = dict(qgis or {})
        launcher = str(qgis_config.get("launcher") or "").strip()
        prefix_path = str(qgis_config.get("prefix_path") or "").strip()
        report: dict[str, Any] = {
            "status": "ok",
            "launcher": launcher,
            "launcher_exists": Path(launcher).exists(),
            "prefix_path": prefix_path,
            "prefix_path_exists": Path(prefix_path).exists(),
            "deep_check": bool(deep),
        }
        if not deep:
            return report

        if launcher and Path(launcher).exists():
            try:
                payload = self._run_qgis_inline(
                    launcher=launcher,
                    prefix_path=prefix_path,
                    expression=(
                        "import json; "
                        "from pineflow_runtime.runtime import QGISRuntime; "
                        f"rt = QGISRuntime(prefix_path={prefix_path!r} or None); "
                        "algorithms = rt.list_algorithms('native:buffer', limit=5); "
                        "print(json.dumps({"
                        "'pyqgis': 'ok', "
                        "'native_buffer_available': any(item.get('id') == 'native:buffer' for item in algorithms), "
                        "'health_execution': 'launcher'"
                        "}, ensure_ascii=False))"
                    ),
                )
                report.update(payload)
                return report
            except Exception as exc:  # pragma: no cover - depends on local QGIS install
                report["status"] = "error"
                report["pyqgis"] = "error"
                report["error"] = str(exc)
                return report

        runtime = QGISRuntime(prefix_path=prefix_path or None)
        try:
            runtime.ensure_ready()
            report["pyqgis"] = "ok"
            report["native_buffer_available"] = any(
                item.get("id") == "native:buffer" for item in runtime.list_algorithms("native:buffer", limit=5)
            )
            report["health_execution"] = "in_process"
        except Exception as exc:  # pragma: no cover - depends on local QGIS install
            report["status"] = "error"
            report["pyqgis"] = "error"
            report["error"] = str(exc)
        finally:
            runtime.shutdown()
        return report

    def search_toolbox(self, *, query: str = "", limit: int = 50, qgis: dict[str, Any] | None = None) -> dict[str, Any]:
        launcher = str((qgis or {}).get("launcher") or "").strip()
        prefix_path = str((qgis or {}).get("prefix_path") or "").strip()
        if launcher and Path(launcher).exists():
            payload = self._run_qgis_inline(
                launcher=launcher,
                prefix_path=prefix_path,
                expression=(
                    "import json; "
                    "from pineflow_runtime.runtime import QGISRuntime; "
                    f"rt = QGISRuntime(prefix_path={prefix_path!r} or None); "
                    f"algorithms = rt.list_algorithms({query!r}, limit={int(limit)}); "
                    "print(json.dumps({'algorithms': algorithms, 'count': len(algorithms)}, ensure_ascii=False))"
                ),
            )
            return make_json_safe(payload)
        runtime = QGISRuntime(prefix_path=prefix_path or None)
        algorithms = runtime.list_algorithms(query, limit=limit)
        return {"algorithms": make_json_safe(algorithms), "count": len(algorithms)}

    def algorithm_help(self, algorithm_id: str, *, qgis: dict[str, Any] | None = None) -> dict[str, Any]:
        launcher = str((qgis or {}).get("launcher") or "").strip()
        prefix_path = str((qgis or {}).get("prefix_path") or "").strip()
        if launcher and Path(launcher).exists():
            payload = self._run_qgis_inline(
                launcher=launcher,
                prefix_path=prefix_path,
                expression=(
                    "import json; "
                    "from pineflow_runtime.runtime import QGISRuntime; "
                    f"rt = QGISRuntime(prefix_path={prefix_path!r} or None); "
                    f"print(json.dumps(rt.algorithm_help({algorithm_id!r}), ensure_ascii=False))"
                ),
            )
            return make_json_safe(payload)
        runtime = QGISRuntime(prefix_path=prefix_path or None)
        return make_json_safe(runtime.algorithm_help(algorithm_id))

    @staticmethod
    def _run_qgis_inline(*, launcher: str, prefix_path: str, expression: str) -> dict[str, Any]:
        env = os.environ.copy()
        if prefix_path:
            env["QGIS_PREFIX_PATH"] = prefix_path
        completed = subprocess.run(
            launcher_command(launcher, "-c", expression),
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(stderr or f"QGIS inline command failed with code {completed.returncode}")
        output = completed.stdout.strip()
        if not output:
            return {}
        value = json.loads(output)
        if not isinstance(value, dict):
            raise RuntimeError("QGIS inline command did not return a JSON object.")
        return value
