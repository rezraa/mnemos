# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: bootstrap_context

Store codebase context so that subsequent tool calls can make
project-aware recommendations.
"""

from __future__ import annotations

import hashlib
from typing import Any

from mnemos.memory.schemas import (
    CodebaseContext,
    PatternFound,
    StructureFound,
)
from mnemos.tools._shared import emit_event, knowledge, memory


def bootstrap_context(
    project_path: str,
    language: str,
    structures_found: list[dict],
    patterns_found: list[dict] | None = None,
    runtime_constraints: list[str] | None = None,
) -> dict:
    """Store codebase context for project-aware recommendations.

    Args:
        project_path: Path to project root.
        language: Primary language of the project.
        structures_found: List of ``{type, location, usage}`` dicts.
        patterns_found: Optional list of ``{pattern, location}`` dicts.
        runtime_constraints: Optional list like
            ``["max memory 512MB", "async/await"]``.

    Returns:
        ``{stored: true, project_id: "xxxx",
          validated: {known_patterns, known_structures, unknown}}``.
    """
    # Generate a deterministic project_id from the path
    project_id = _project_id_from_path(project_path)

    # Build schema objects
    structure_objs = [
        StructureFound(
            type=s.get("type", "unknown"),
            location=s.get("location", ""),
            usage=s.get("usage", ""),
        )
        for s in structures_found
    ]

    pattern_objs: list[PatternFound] = []
    if patterns_found:
        pattern_objs = [
            PatternFound(
                pattern=p.get("pattern", ""),
                location=p.get("location", ""),
            )
            for p in patterns_found
        ]

    constraints_str: str | None = None
    if runtime_constraints:
        constraints_str = "; ".join(runtime_constraints)

    # Create and persist context
    context = CodebaseContext(
        project_id=project_id,
        project_path=project_path,
        language=language,
        structures_found=structure_objs,
        patterns_found=pattern_objs,
        runtime_constraints=constraints_str,
    )

    memory.set_context(context)

    # Validate against knowledge base: classify as known vs unknown
    validated = _validate_against_knowledge(structure_objs, pattern_objs)

    emit_event("context_bootstrapped", {
        "project_id": project_id,
        "project_path": project_path,
        "language": language,
        "structures_count": len(structure_objs),
        "patterns_count": len(pattern_objs),
    })

    return {
        "stored": True,
        "project_id": project_id,
        "validated": validated,
    }


def _project_id_from_path(path: str) -> str:
    """Generate a short deterministic ID from a project path."""
    return hashlib.sha256(path.encode()).hexdigest()[:12]


def _validate_against_knowledge(
    structures: list[StructureFound],
    patterns: list[PatternFound],
) -> dict[str, Any]:
    """Cross-reference discovered structures and patterns with the knowledge
    base.  Returns counts of known vs unknown items."""

    all_kb_patterns = knowledge.get_all_patterns()
    kb_pattern_names: set[str] = set()
    kb_pattern_ids: set[str] = set()
    for p in all_kb_patterns:
        kb_pattern_names.add(p.get("name", "").lower())
        kb_pattern_ids.add(p.get("id", "").lower())

    all_kb_structures = knowledge.get_all_structures()
    kb_structure_ids: set[str] = set()
    for s in all_kb_structures:
        kb_structure_ids.add(s.get("id", "").lower())
        kb_structure_ids.add(s.get("name", "").lower())

    known_structures: list[str] = []
    unknown_structures: list[str] = []
    for sf in structures:
        t = sf.type.lower()
        if t in kb_structure_ids or any(t in sid for sid in kb_structure_ids):
            known_structures.append(sf.type)
        else:
            unknown_structures.append(sf.type)

    known_patterns: list[str] = []
    unknown_patterns: list[str] = []
    for pf in patterns:
        p = pf.pattern.lower()
        if (
            p in kb_pattern_names
            or p in kb_pattern_ids
            or any(p in name for name in kb_pattern_names)
        ):
            known_patterns.append(pf.pattern)
        else:
            unknown_patterns.append(pf.pattern)

    return {
        "known_structures": known_structures,
        "known_patterns": known_patterns,
        "unknown": unknown_structures + unknown_patterns,
    }
