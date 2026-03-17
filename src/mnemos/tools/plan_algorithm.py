# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: plan_algorithm

Recommend algorithm + data structure based on agent-identified structural
signals, explicit structure guesses, and optional constraints.

The agent (LLM) reads the problem/code and identifies signals.  This tool
matches those signals against decision_rules.json, retrieves knowledge
slices from structures.json, filters by constraints using complexities.json,
and checks memory for regressions.
"""

from __future__ import annotations

from typing import Any

from mnemos.tools._shared import (
    emit_event,
    knowledge,
    memory,
    validate_suggestion,
)


def plan_algorithm(
    problem: str,
    structural_signals: list[str] | None = None,
    constraints: dict | None = None,
    structures: list[str] | None = None,
    project_id: str | None = None,
) -> dict:
    """Recommend algorithm + DS based on structural signals and constraints.

    Args:
        problem: Structural description of the problem from the agent.
        structural_signals: Agent-identified signals, e.g.
            ["unsorted-pair-search", "need-indices"].
        constraints: Optional dict with keys like n, input_size, space.
        structures: Agent's guess of relevant structures, e.g.
            ["hashmap", "heap"].
        project_id: Optional project ID for codebase context filtering.

    Returns:
        Tight JSON with keys: matched_rules, knowledge, filtered_out,
        context, memory.
    """
    # 1. Match structural signals against decision_rules.json
    matched_rules: list[dict[str, Any]] = []
    consider: list[dict[str, Any]] = []

    if structural_signals:
        rule_matches = knowledge.match_structural_signals(structural_signals)
        for rm in rule_matches:
            rule = rm["rule"]
            rec_pat = rm.get("recommended_pattern")

            rule_entry: dict[str, Any] = {
                "signal": rm["signal"],
                "rule_id": rule["id"],
                "recommended": rule.get("recommended_pattern", ""),
                "ds": rm.get("recommended_structure", ""),
                "alternatives": [a.get("id", "") for a in rm.get("alternatives", [])],
            }
            matched_rules.append(rule_entry)

            # Add recommended pattern to consider list
            if rec_pat:
                consider.append({
                    "pattern_id": rec_pat["id"],
                    "name": rec_pat.get("name", rec_pat["id"]),
                    "complexity": rec_pat.get("complexity", {}),
                    "structure_id": rec_pat.get("structure_id", ""),
                    "ds": rm.get("recommended_structure", ""),
                    "source": "decision_rule",
                    "rule_id": rule["id"],
                    "score": 1.0,
                })

            # Add alternatives
            for alt in rm.get("alternatives", []):
                if "complexity" in alt:
                    consider.append({
                        "pattern_id": alt["id"],
                        "name": alt.get("name", alt["id"]),
                        "complexity": alt.get("complexity", {}),
                        "structure_id": alt.get("structure_id", ""),
                        "ds": alt.get("structure_id", ""),
                        "source": "alternative",
                        "rule_id": rule["id"],
                        "score": 0.7,
                    })

    # 2. If structures provided, retrieve those with full pattern details
    knowledge_slice: dict[str, Any] = {}
    if structures:
        for sid in structures:
            struct = knowledge.get_structure(sid)
            if struct:
                patterns = []
                for pat in struct.get("patterns", []):
                    patterns.append({
                        "id": pat["id"],
                        "name": pat.get("name", pat["id"]),
                        "complexity": pat.get("complexity", {}),
                        "structural_signals": pat.get("structural_signals", []),
                        "applies_when": pat.get("applies_when", []),
                    })
                knowledge_slice[sid] = {
                    "name": struct.get("name", sid),
                    "operations": struct.get("operations", {}),
                    "patterns": patterns,
                }

    # 3. Filter by constraints using complexities.json
    filtered_out: list[dict[str, Any]] = []
    if constraints and consider:
        normalized = dict(constraints)
        if "n" in normalized and "input_size" not in normalized:
            normalized["input_size"] = normalized.pop("n")

        surviving, removed = knowledge.filter_by_constraints(consider, normalized)
        filtered_out = [
            {"pattern_id": r.get("pattern_id", ""), "name": r.get("name", ""),
             "reason": r.get("filter_reason", "")}
            for r in removed
        ]
        consider = surviving

    # 4. Check memory for regressions on matched patterns
    memory_info: dict[str, Any] = {}
    regressions_found: list[dict[str, Any]] = []
    for c in consider:
        pid = c.get("pattern_id", "")
        ds = c.get("ds", c.get("structure_id", ""))
        if pid and ds:
            reg = memory.check_regression(pattern=pid, ds=ds)
            if reg:
                regressions_found.append({
                    "pattern": pid,
                    "ds": ds,
                    "description": reg.description,
                    "severity": reg.severity.value,
                })
    if regressions_found:
        memory_info["regressions"] = regressions_found

    # Recent decisions for context
    if project_id:
        recent = memory.get_decisions(project_id=project_id)
        if recent:
            memory_info["past_decisions"] = len(recent)
            memory_info["last_pattern"] = recent[-1].pattern_chosen

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

    # 6. Validate suggestions before returning
    consider = validate_suggestion(
        consider, constraints=constraints, project_id=project_id,
    )

    result = {
        "matched_rules": matched_rules,
        "knowledge": knowledge_slice,
        "consider": consider,
        "filtered_out": filtered_out,
        "context": context_info,
        "memory": memory_info,
    }

    emit_event("plan_algorithm", {
        "problem": problem[:120],
        "signals": structural_signals or [],
        "matched_rules_count": len(matched_rules),
        "candidates_count": len(consider),
        "filtered_out_count": len(filtered_out),
    })

    return result
