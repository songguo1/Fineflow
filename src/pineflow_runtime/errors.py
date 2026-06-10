"""Service-local error types."""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """Base error with a stable machine-readable code."""

    def __init__(self, message: str, *, code: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = str(code)
        self.data = dict(data or {})


class QGISRuntimeError(ServiceError):
    def __init__(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="pineflow_runtime_error", data=data)


class ToolValidationError(ServiceError):
    def __init__(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="tool_validation_error", data=data)


class ToolExecutionError(ServiceError):
    def __init__(self, message: str, *, data: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="tool_execution_error", data=data)
