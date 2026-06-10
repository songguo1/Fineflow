"""Session memory retrieval helpers for ReAct prompt context."""

from __future__ import annotations

from typing import Any

from pineflow_agent.core.workspace_state import WorkspaceStateStore


def read_session_memory(toolbox: Any, *, user_request: str = "") -> str:
    workspace = getattr(toolbox, "workspace", None)
    if workspace is None:
        return ""
    full = WorkspaceStateStore(workspace).read_memory()
    if not full:
        return ""
    if user_request:
        return relevant_memory_segments(full, user_request)
    blocks = full.split("\n---\n")
    return "\n---\n".join(blocks[-2:]).strip() if len(blocks) > 2 else full.strip()


def relevant_memory_segments(session_memory: str, user_request: str, max_chars: int = 600) -> str:
    """Extract memory blocks most relevant to the current user request."""
    if not session_memory or not user_request:
        return session_memory or ""
    keywords = set(user_request.lower().split())
    keywords -= {"the", "a", "an", "to", "of", "in", "on", "at", "by", "for", "with", "and", "or", "is", "are", "请", "的"}
    if not keywords:
        blocks = session_memory.split("\n---\n")
        return "\n---\n".join(blocks[-2:]).strip() if len(blocks) > 2 else session_memory[:max_chars]

    blocks = session_memory.split("\n---\n")
    scored: list[tuple[int, str]] = []
    for block in blocks:
        block_lower = block.lower()
        score = sum(1 for kw in keywords if kw in block_lower)
        if score > 0:
            scored.append((score, block))
    scored.sort(key=lambda item: item[0], reverse=True)
    result_parts: list[str] = []
    total = 0
    for _, block in scored:
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                result_parts.append(block[:remaining] + "\n...")
            break
        result_parts.append(block)
        total += len(block)
    return "\n---\n".join(result_parts).strip() if result_parts else session_memory[:max_chars]
