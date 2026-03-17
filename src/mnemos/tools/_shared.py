# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Shared state and utilities for all Mnemos MCP tools.

Every tool module imports from here to get access to the singleton
KnowledgeLoader, MemoryStore, and the validate_suggestion() pre-return filter.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from mnemos.knowledge.loader import KnowledgeLoader, _rank
from mnemos.memory.store import MemoryStore

# ---------------------------------------------------------------------------
# Singletons — shared across all tool modules
# ---------------------------------------------------------------------------

knowledge: KnowledgeLoader = KnowledgeLoader()
memory: MemoryStore = MemoryStore()


def get_memory(conn: Any = None) -> MemoryStore:
    """Return the appropriate memory store for the current mode.

    Args:
        conn: If provided, returns a GraphMemoryStore backed by this
              Kuzu/LadybugDB connection. If None, returns the JSON singleton.
    """
    if conn is None:
        return memory
    from mnemos.memory.graph_store import GraphMemoryStore
    return GraphMemoryStore(conn)


def get_knowledge(conn: Any = None) -> KnowledgeLoader:
    """Return the appropriate knowledge loader for the current mode.

    Args:
        conn: If provided, returns a GraphKnowledgeLoader backed by this
              Kuzu/LadybugDB connection. If None, returns the JSON singleton.
    """
    if conn is None:
        return knowledge
    from mnemos.knowledge.graph_loader import GraphKnowledgeLoader
    return GraphKnowledgeLoader(conn)

# ---------------------------------------------------------------------------
# Event system — file-based for cross-process dashboard communication
# ---------------------------------------------------------------------------

_event_listeners: list[Callable[[str, dict], None]] = []


def _events_file() -> Path:
    """Return the path to the shared events JSONL file."""
    env = os.environ.get("MNEMOS_MEMORY_DIR")
    base = Path(env) if env else Path.home() / ".mnemos" / "memory"
    return base / "events.jsonl"


def on_event(callback: Callable[[str, dict], None]) -> None:
    """Register a callback that receives (event_name, payload) on every emit."""
    _event_listeners.append(callback)


def emit_event(event_name: str, payload: dict[str, Any]) -> None:
    """Fire an event to all registered listeners and append to events file.

    The events file (events.jsonl) is the cross-process bridge between the
    MCP server (which emits events) and the dashboard (which reads them).
    """
    # In-process listeners (if any)
    for cb in _event_listeners:
        try:
            cb(event_name, payload)
        except Exception:
            pass

    # File-based broadcast for dashboard
    try:
        event = {
            "type": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        ef = _events_file()
        ef.parent.mkdir(parents=True, exist_ok=True)
        with open(ef, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass  # best-effort — never break tool execution


# ---------------------------------------------------------------------------
# validate_suggestion — internal pre-return filter
# ---------------------------------------------------------------------------

def validate_suggestion(
    suggestions: list[dict[str, Any]],
    constraints: dict[str, Any] | None = None,
    project_id: str | None = None,
    kb: Any = None,
    mem: Any = None,
) -> list[dict[str, Any]]:
    """Validate a list of suggestion dicts before returning to the caller.

    Checks performed:
    1. Constraint violations  — demote suggestions whose complexity exceeds
       what *constraints* allow (using input_size_guidelines from JSON).
    2. Memory contradictions  — demote if the suggestion matches a known
       regression in MemoryStore.
    3. Codebase conflicts     — remove if the suggested DS or pattern is
       explicitly banned in the project's CodebaseContext runtime_constraints.

    Each suggestion dict is expected to have at least:
        name (str), complexity (dict with 'time'/'space'), and optionally
        pattern_id / ds / structure_id.
    """
    if not suggestions:
        return suggestions

    validated: list[dict[str, Any]] = []

    _mem = mem or memory

    # Load codebase context once if project_id given
    ctx = _mem.get_context(project_id) if project_id else None
    banned_terms: set[str] = set()
    if ctx and ctx.runtime_constraints:
        rc_lower = ctx.runtime_constraints.lower()
        if "no " in rc_lower or "ban" in rc_lower or "avoid" in rc_lower:
            banned_terms = {
                w.strip().lower()
                for w in rc_lower.replace(",", " ").split()
                if len(w.strip()) > 2
            }

    for suggestion in suggestions:
        name = suggestion.get("name", "")
        name_lower = name.lower().replace(" ", "-")
        complexity = suggestion.get("complexity", {})
        time_c = complexity.get("time", "")
        space_c = complexity.get("space", "")
        pattern_id = suggestion.get("pattern_id", suggestion.get("id", ""))
        ds = suggestion.get("structure_id", suggestion.get("ds", ""))

        skip = False
        warnings: list[str] = list(suggestion.get("warnings", []))

        # ----- 1. Constraint violations (data-driven) -----
        if constraints:
            n = constraints.get("input_size") or constraints.get("n")
            if n is not None and isinstance(n, (int, float)):
                n = int(n)
                _kb = kb or knowledge
                max_rank = _kb.max_feasible_complexity_rank(n)
                time_rank = _rank(time_c) if time_c else 0
                if time_c and time_rank > max_rank:
                    warnings.append(
                        f"CONSTRAINT VIOLATION: {time_c} infeasible for n={n:,}"
                    )
                    suggestion["demoted"] = True

            max_space = constraints.get("space")
            if max_space and space_c:
                if _rank(space_c) > _rank(max_space):
                    warnings.append(
                        f"SPACE VIOLATION: {space_c} exceeds max {max_space}"
                    )
                    suggestion["demoted"] = True

        # ----- 2. Memory contradictions -----
        if pattern_id and ds:
            regression = _mem.check_regression(pattern=str(pattern_id), ds=str(ds))
            if regression:
                warnings.append(
                    f"REGRESSION WARNING: {pattern_id}+{ds} regressed previously — "
                    f"{regression.description}"
                )
                suggestion["demoted"] = True

        # ----- 3. Codebase conflicts -----
        if banned_terms:
            combined = f"{name_lower} {pattern_id} {ds}".lower()
            for term in banned_terms:
                if term in combined:
                    warnings.append(
                        f"CODEBASE CONFLICT: '{term}' appears banned in project constraints"
                    )
                    skip = True
                    break

        if not skip:
            suggestion["warnings"] = warnings
            validated.append(suggestion)

    # Sort: non-demoted first, then by score descending
    validated.sort(
        key=lambda s: (s.get("demoted", False), -(s.get("score", 0))),
    )
    return validated
