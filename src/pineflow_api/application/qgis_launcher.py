"""Shared helpers for invoking QGIS Python launcher commands."""

from __future__ import annotations


def launcher_command(launcher: str, *args: str) -> list[str]:
    if str(launcher).lower().endswith(".bat"):
        return ["cmd", "/c", launcher, *args]
    return [launcher, *args]
