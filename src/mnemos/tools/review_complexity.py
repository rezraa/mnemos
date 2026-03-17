# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: review_complexity

Accept the agent's analysis of code (detected pattern, structures, complexity)
and return feasibility assessment + alternatives from the knowledge base.

No code param.  No language param.  The agent already analyzed the code.
"""

from __future__ import annotations

from typing import Any

from mnemos.knowledge.loader import _rank
from mnemos.tools._shared import (
    emit_event,
    knowledge,
    memory,
    validate_suggestion,
)


def review_complexity(
    detected_pattern: str | None = None,
    detected_structures: list[str] | None = None,
    detected_complexity: str | None = None,
    constraints: dict | None = None,
    project_id: str | None = None,
) -> dict:
    """Review complexity based on the agent's analysis of code.

    Args:
        detected_pattern: Pattern the agent identified, e.g. "nested-loop".
        detected_structures: Structures the agent found, e.g. ["array"].
        detected_complexity: Complexity the agent estimated, e.g. "O(n^2)".
        constraints: Optional dict with keys like n, input_size, space.
        project_id: Optional project ID for codebase context.

    Returns:
        Dict with keys: detected, feasibility, alternatives, context, memory.
    """
    detected_info: dict[str, Any] = {}
    if detected_pattern:
        detected_info["pattern"] = detected_pattern
    if detected_structures:
        detected_info["structures"] = detected_structures
    if detected_complexity:
        detected_info["complexity"] = detected_complexity

    # 1. Look up detected_pattern in knowledge base
    pattern_info: dict[str, Any] | None = None
    alternatives: list[dict[str, Any]] = []

    if detected_pattern:
        pattern_info = knowledge.get_pattern(detected_pattern)
        if pattern_info:
            detected_info["known_pattern"] = {
                "id": pattern_info["id"],
                "name": pattern_info.get("name", ""),
                "complexity": pattern_info.get("complexity", {}),
                "structure_id": pattern_info.get("structure_id", ""),
            }

            # Get alternatives with when_better reasoning
            alts = knowledge.get_alternatives(detected_pattern)
            for alt in alts:
                alt_complexity = alt.get("complexity", {})
                alt_time = alt_complexity.get("time", "") if alt_complexity else ""

                alt_entry: dict[str, Any] = {
                    "pattern_id": alt["id"],
                    "name": alt.get("name", alt["id"]),
                    "complexity": alt_complexity,
                    "when_better": alt.get("when_better"),
                    "structure_id": "",
                    "ds": "",
                }

                # Check if this alternative is actually better
                if detected_complexity and alt_time:
                    if _rank(alt_time) < _rank(detected_complexity):
                        alt_entry["improvement"] = f"{detected_complexity} -> {alt_time}"

                # Resolve structure_id
                full_alt = knowledge.get_pattern(alt["id"])
                if full_alt:
                    alt_entry["structure_id"] = full_alt.get("structure_id", "")
                    alt_entry["ds"] = full_alt.get("structure_id", "")

                alternatives.append(alt_entry)

    # 2. Look up detected_structures for their patterns and operation costs
    structure_info: dict[str, Any] = {}
    if detected_structures:
        for sid in detected_structures:
            struct = knowledge.get_structure(sid)
            if struct:
                structure_info[sid] = {
                    "operations": struct.get("operations", {}),
                    "pattern_count": len(struct.get("patterns", [])),
                }

    # 3. Feasibility check against constraints
    feasibility: dict[str, Any] = {}
    if detected_complexity and constraints:
        normalized = dict(constraints)
        if "n" in normalized and "input_size" not in normalized:
            normalized["input_size"] = normalized.pop("n")

        # Create a dummy pattern entry for filtering
        dummy = [{"complexity": {"time": detected_complexity}, "name": "current"}]
        surviving, removed = knowledge.filter_by_constraints(dummy, normalized)
        feasibility["is_feasible"] = len(surviving) > 0
        if removed:
            feasibility["reason"] = removed[0].get("filter_reason", "")
    elif detected_complexity:
        feasibility["is_feasible"] = True

    # 4. Filter alternatives by constraints if provided
    filtered_out: list[dict[str, Any]] = []
    if constraints and alternatives:
        normalized = dict(constraints)
        if "n" in normalized and "input_size" not in normalized:
            normalized["input_size"] = normalized.pop("n")
        surviving, removed = knowledge.filter_by_constraints(alternatives, normalized)
        filtered_out = [
            {"pattern_id": r.get("pattern_id", ""), "reason": r.get("filter_reason", "")}
            for r in removed
        ]
        alternatives = surviving

    # 5. Check memory for regressions
    memory_info: dict[str, Any] = {}
    if detected_pattern:
        ds = ""
        if pattern_info:
            ds = pattern_info.get("structure_id", "")
        if ds:
            reg = memory.check_regression(pattern=detected_pattern, ds=ds)
            if reg:
                memory_info["regressions"] = [{
                    "pattern": detected_pattern,
                    "ds": ds,
                    "description": reg.description,
                    "severity": reg.severity.value,
                }]

    # 6. Codebase context
    context_info: dict[str, Any] = {}
    if project_id:
        ctx = memory.get_context(project_id)
        if ctx:
            context_info = {
                "project_id": ctx.project_id,
                "runtime_constraints": ctx.runtime_constraints,
            }

    # 7. Validate alternative suggestions
    alternatives = validate_suggestion(
        alternatives, constraints=constraints, project_id=project_id,
    )

    result = {
        "detected": detected_info,
        "feasibility": feasibility,
        "alternatives": alternatives,
        "structure_info": structure_info,
        "filtered_out": filtered_out,
        "context": context_info,
        "memory": memory_info,
    }

    emit_event("review_complexity", {
        "pattern": detected_pattern or "?",
        "complexity": detected_complexity or "?",
        "feasible": feasibility.get("feasible", True),
        "alternatives_count": len(alternatives),
    })

    return result
