"""Hook pipeline registry for the ReAct GIS agent."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pineflow_agent.orchestration.hooks.contexts import HookPoint

_log = logging.getLogger(__name__)

class HookExecutionError(RuntimeError):
    """Raised when a critical hook fails and execution must stop."""


class _RegisteredHook:
    __slots__ = ("name", "point", "fn", "priority", "critical")

    def __init__(
        self,
        name: str,
        point: HookPoint,
        fn: Callable[..., Any],
        priority: int = 100,
        critical: bool = False,
    ) -> None:
        self.name = name
        self.point = point
        self.fn = fn
        self.priority = priority
        self.critical = bool(critical)


class HookPipeline:
    """Ordered pipeline of lifecycle hooks for the agent runtime."""

    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[_RegisteredHook]] = {p: [] for p in HookPoint}

    def register(
        self,
        point: HookPoint,
        fn: Callable[..., Any],
        *,
        name: str = "",
        priority: int = 100,
        replace: bool = False,
        critical: bool = False,
    ) -> None:
        point = _coerce_hook_point(point)
        hook_name = name or getattr(fn, "__name__", "unnamed")
        registered = _RegisteredHook(
            name=hook_name,
            point=point,
            fn=fn,
            priority=priority,
            critical=critical,
        )
        hooks = self._hooks.setdefault(point, [])
        for index, existing in enumerate(hooks):
            if existing.name != hook_name:
                continue
            if existing.fn is fn:
                return
            if replace:
                hooks[index] = registered
                hooks.sort(key=lambda h: h.priority)
                return
            raise ValueError(f"Hook {hook_name!r} is already registered for {point.value}.")
        hooks.append(registered)
        hooks.sort(key=lambda h: h.priority)

    def emit(self, point: HookPoint, ctx: Any) -> Any:
        """Run all hooks registered for *point*, passing *ctx* through the chain."""
        for registered in self._hooks.get(point, []):
            try:
                result = registered.fn(ctx)
                if result is not None:
                    ctx = result
            except Exception as exc:
                _log.warning("Hook %r at point %s raised an exception", registered.name, registered.point.value, exc_info=True)
                if registered.critical:
                    raise HookExecutionError(
                        f"Critical hook {registered.name!r} at point {registered.point.value} failed."
                    ) from exc
        return ctx

    def hook_names(self, point: HookPoint) -> list[str]:
        return [h.name for h in self._hooks.get(point, [])]


# Module-level registry for @register_hook decorator
_GLOBAL_PIPELINE: HookPipeline | None = None


def register_hook(
    point: HookPoint | str,
    *,
    name: str = "",
    priority: int = 100,
    replace: bool = False,
    critical: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a function and register it with the global hook pipeline."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        get_pipeline().register(
            _coerce_hook_point(point),
            fn,
            name=name,
            priority=priority,
            replace=replace,
            critical=critical,
        )
        return fn

    return decorator


def get_pipeline() -> HookPipeline:
    global _GLOBAL_PIPELINE
    if _GLOBAL_PIPELINE is None:
        _GLOBAL_PIPELINE = HookPipeline()
        _register_builtin_hooks(_GLOBAL_PIPELINE)
    return _GLOBAL_PIPELINE

def get_pipeline() -> HookPipeline:
    global _GLOBAL_PIPELINE
    if _GLOBAL_PIPELINE is None:
        from pineflow_agent.orchestration.hooks.builtins import _register_builtin_hooks

        _GLOBAL_PIPELINE = HookPipeline()
        _register_builtin_hooks(_GLOBAL_PIPELINE)
    return _GLOBAL_PIPELINE

def _coerce_hook_point(point: HookPoint | str) -> HookPoint:
    if isinstance(point, HookPoint):
        return point
    return HookPoint(str(point or ""))
