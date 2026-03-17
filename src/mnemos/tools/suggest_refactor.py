# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: suggest_refactor

Suggest refactoring alternatives based on the agent's diagnosis of the
current code pattern and a target complexity.

No code param.  No language param.  The agent already diagnosed the issue.
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


def suggest_refactor(
    current_pattern: str | None = None,
    current_structure: str | None = None,
    current_complexity: str | None = None,
    target_complexity: str | None = None,
    constraints: dict | None = None,
    project_id: str | None = None,
) -> dict:
    """Suggest refactoring alternatives given the agent's diagnosis.

    Args:
        current_pattern: Pattern the agent identified, e.g. "nested-scan".
        current_structure: Current DS, e.g. "array".
        current_complexity: Current complexity, e.g. "O(n^2)".
        target_complexity: Desired complexity, e.g. "O(n)".
        constraints: Optional dict with keys like n, input_size, space.
        project_id: Optional project ID for codebase context.

    Returns:
        Dict with keys: current, suggestions, filtered_out, context, memory.
    """
    current_info: dict[str, Any] = {}
    if current_pattern:
        current_info["pattern"] = current_pattern
    if current_structure:
        current_info["structure"] = current_structure
    if current_complexity:
        current_info["complexity"] = current_complexity
    if target_complexity:
        current_info["target"] = target_complexity

    # 1. Look up current_pattern -> get alternatives from knowledge base
    suggestions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    if current_pattern:
        alts = knowledge.get_alternatives(current_pattern)
        for alt in alts:
            alt_id = alt.get("id", "")
            if alt_id in seen_ids:
                continue
            seen_ids.add(alt_id)

            alt_complexity = alt.get("complexity", {})
            alt_time = alt_complexity.get("time", "") if alt_complexity else ""

            # Only suggest if it's actually better (or if we can't compare)
            if current_complexity and alt_time:
                if _rank(alt_time) >= _rank(current_complexity):
                    continue

            # Resolve full pattern for structure_id
            full_alt = knowledge.get_pattern(alt_id)
            structure_id = full_alt.get("structure_id", "") if full_alt else ""

            entry: dict[str, Any] = {
                "pattern_id": alt_id,
                "name": alt.get("name", alt_id),
                "complexity": alt_complexity,
                "when_better": alt.get("when_better"),
                "structure_id": structure_id,
                "ds": structure_id,
                "score": 1.0,
            }

            if current_complexity and alt_time:
                entry["improvement"] = f"{current_complexity} -> {alt_time}"

            suggestions.append(entry)

    # 2. If current_structure provided, also look at patterns from that
    #    structure that might be better
    if current_structure:
        struct = knowledge.get_structure(current_structure)
        if struct:
            for pat in struct.get("patterns", []):
                pid = pat["id"]
                if pid in seen_ids or pid == current_pattern:
                    continue

                pat_complexity = pat.get("complexity", {})
                pat_time = pat_complexity.get("time", "")

                if current_complexity and pat_time:
                    if _rank(pat_time) >= _rank(current_complexity):
                        continue

                seen_ids.add(pid)
                suggestions.append({
                    "pattern_id": pid,
                    "name": pat.get("name", pid),
                    "complexity": pat_complexity,
                    "when_better": pat.get("applies_when", [])[:2] or None,
                    "structure_id": current_structure,
                    "ds": current_structure,
                    "improvement": f"{current_complexity} -> {pat_time}" if current_complexity and pat_time else None,
                    "score": 0.7,
                })

    # 3. Filter by constraints + target_complexity
    filtered_out: list[dict[str, Any]] = []
    if suggestions:
        filter_constraints = dict(constraints or {})
        if target_complexity:
            filter_constraints["target_complexity"] = target_complexity

        if filter_constraints:
            surviving, removed = knowledge.filter_by_constraints(
                suggestions, filter_constraints,
            )
            filtered_out = [
                {"pattern_id": r.get("pattern_id", ""), "name": r.get("name", ""),
                 "reason": r.get("filter_reason", "")}
                for r in removed
            ]
            suggestions = surviving

    # 4. Check memory for past refactors and regressions
    memory_info: dict[str, Any] = {}
    if project_id:
        corrections = memory.get_corrections(project_id=project_id)
        if corrections:
            memory_info["past_corrections"] = [
                {
                    "from": c.original_pattern,
                    "to": c.corrected_pattern,
                    "reason": c.reason,
                }
                for c in corrections[-3:]
            ]

    for s in suggestions:
        pid = s.get("pattern_id", "")
        ds = s.get("ds", "")
        if pid and ds:
            reg = memory.check_regression(pattern=pid, ds=ds)
            if reg:
                memory_info.setdefault("regressions_on_suggestions", []).append({
                    "pattern": pid,
                    "ds": ds,
                    "description": reg.description,
                    "severity": reg.severity.value,
                })

    # 5. Codebase context
    context_info: dict[str, Any] = {}
    if project_id:
        ctx = memory.get_context(project_id)
        if ctx:
            context_info = {
                "project_id": ctx.project_id,
                "structures_in_use": [s.type for s in ctx.structures_found],
                "patterns_in_use": [p.pattern for p in ctx.patterns_found],
                "runtime_constraints": ctx.runtime_constraints,
            }

    # 6. Validate
    suggestions = validate_suggestion(
        suggestions,
        constraints=constraints,
        project_id=project_id,
    )

    # Sort by complexity improvement (best first)
    suggestions.sort(
        key=lambda s: (s.get("demoted", False), _rank(s.get("complexity", {}).get("time", "O(n)"))),
    )

    result = {
        "current": current_info,
        "suggestions": suggestions,
        "filtered_out": filtered_out,
        "context": context_info,
        "memory": memory_info,
    }

    emit_event("suggest_refactor", {
        "current_pattern": current_pattern or "?",
        "current_complexity": current_complexity or "?",
        "target_complexity": target_complexity or "any",
        "suggestions_count": len(suggestions),
    })

    return result
