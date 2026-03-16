# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""Mnemos MCP Server — Algorithmic Reasoning Memory for LLMs.

Uses FastMCP's decorator-based tool registration to expose five tools:

    plan_algorithm      — recommend algorithm + DS for agent-identified signals
    review_complexity   — assess feasibility of agent-detected complexity
    suggest_refactor    — suggest alternatives given agent's diagnosis
    log_decision        — log an algorithmic decision to memory
    bootstrap_context   — store codebase context for project-aware recommendations
"""

from __future__ import annotations

import json as _json
from typing import Any, Union

from fastmcp import FastMCP


def _coerce(val, expected_type):
    """Coerce JSON-encoded strings to their native types.

    Some MCP clients send list/dict params as JSON strings on the first call.
    This silently handles both native types and string-encoded JSON.
    """
    if val is None:
        return None
    if isinstance(val, str) and expected_type in (list, dict):
        try:
            parsed = _json.loads(val)
            if isinstance(parsed, expected_type):
                return parsed
        except (ValueError, TypeError):
            pass
    return val

from mnemos.tools.plan_algorithm import plan_algorithm as _plan_algorithm
from mnemos.tools.review_complexity import review_complexity as _review_complexity
from mnemos.tools.suggest_refactor import suggest_refactor as _suggest_refactor
from mnemos.tools.log_decision import log_decision as _log_decision
from mnemos.tools.bootstrap_context import bootstrap_context as _bootstrap_context

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("mnemos", instructions="Algorithmic Reasoning Memory for LLMs")


# ---------------------------------------------------------------------------
# Tool registrations — thin wrappers that delegate to the tool modules
# ---------------------------------------------------------------------------

@mcp.tool()
def plan_algorithm(
    problem: str,
    structural_signals: Union[list[str], str, None] = None,
    constraints: Union[dict, str, None] = None,
    structures: Union[list[str], str, None] = None,
    project_id: str | None = None,
) -> dict:
    """Recommend algorithm + DS based on structural signals and constraints.

    The agent reads the problem, identifies structural signals, and passes them here.
    This tool matches signals against decision_rules.json, retrieves knowledge
    slices, and filters by constraints.

    Args:
        problem: Structural description of the problem from the agent.
        structural_signals: Agent-identified signals, e.g. ["unsorted-pair-search"].
        constraints: Optional dict with keys like n, input_size, space.
        structures: Agent's guess of relevant structures, e.g. ["hashmap"].
        project_id: Optional project ID for codebase context filtering.

    Returns tight JSON: matched_rules[], knowledge{}, consider[], filtered_out[], context{}, memory{}
    """
    return _plan_algorithm(
        problem,
        structural_signals=_coerce(structural_signals, list),
        constraints=_coerce(constraints, dict),
        structures=_coerce(structures, list),
        project_id=project_id,
    )


@mcp.tool()
def review_complexity(
    detected_pattern: str | None = None,
    detected_structures: Union[list[str], str, None] = None,
    detected_complexity: str | None = None,
    constraints: Union[dict, str, None] = None,
    project_id: str | None = None,
) -> dict:
    """Review complexity based on the agent's analysis of code.

    The agent reads the code, identifies the pattern and estimates complexity.
    This tool checks feasibility against constraints, finds alternatives, and
    checks memory for regressions.

    Args:
        detected_pattern: Pattern the agent found, e.g. "nested-loop".
        detected_structures: Structures the agent found, e.g. ["array"].
        detected_complexity: Complexity the agent estimated, e.g. "O(n^2)".
        constraints: Optional dict with keys like n, input_size, space.
        project_id: Optional project ID for codebase context.

    Returns: detected{}, feasibility{}, alternatives[], structure_info{}, context{}, memory{}
    """
    return _review_complexity(
        detected_pattern=detected_pattern,
        detected_structures=_coerce(detected_structures, list),
        detected_complexity=detected_complexity,
        constraints=_coerce(constraints, dict),
        project_id=project_id,
    )


@mcp.tool()
def suggest_refactor(
    current_pattern: str | None = None,
    current_structure: str | None = None,
    current_complexity: str | None = None,
    target_complexity: str | None = None,
    constraints: Union[dict, str, None] = None,
    project_id: str | None = None,
) -> dict:
    """Suggest refactoring alternatives given the agent's diagnosis.

    The agent reads the code, diagnoses the issue. This tool looks up alternatives,
    filters by target complexity and constraints, checks memory.

    Args:
        current_pattern: Pattern the agent identified, e.g. "nested-scan".
        current_structure: Current DS, e.g. "array".
        current_complexity: Current complexity, e.g. "O(n^2)".
        target_complexity: Desired complexity, e.g. "O(n)".
        constraints: Optional dict with keys like n, input_size, space.
        project_id: Optional project ID for codebase context.
    """
    return _suggest_refactor(
        current_pattern=current_pattern,
        current_structure=current_structure,
        current_complexity=current_complexity,
        target_complexity=target_complexity,
        constraints=_coerce(constraints, dict),
        project_id=project_id,
    )


@mcp.tool()
def log_decision(
    mode: str,
    problem: str,
    pattern_chosen: str,
    ds_chosen: str,
    outcome: str,
    project_id: str | None = None,
    regression_details: str | None = None,
    correction_details: str | None = None,
) -> dict:
    """Log an algorithmic decision and its outcome to memory.

    Args:
        mode: Context — one of "plan", "review", "maintain".
        problem: What problem was being solved.
        pattern_chosen: Algorithm pattern selected.
        ds_chosen: Data structure selected.
        outcome: Result — one of "accepted", "rejected", "regressed".
        project_id: Optional project this decision belongs to.
        regression_details: Details if outcome is "regressed".
        correction_details: Details if the decision was later corrected.

    Returns: {logged: true, decision_id: "d-xxxx"}
    """
    return _log_decision(
        mode=mode,
        problem=problem,
        pattern_chosen=pattern_chosen,
        ds_chosen=ds_chosen,
        outcome=outcome,
        project_id=project_id,
        regression_details=regression_details,
        correction_details=correction_details,
    )


@mcp.tool()
def bootstrap_context(
    project_path: str,
    language: str,
    structures_found: Union[list[dict], str] = "[]",
    patterns_found: Union[list[dict], str, None] = None,
    runtime_constraints: Union[list[str], str, None] = None,
) -> dict:
    """Store codebase context for project-aware recommendations.

    Args:
        project_path: Path to project root.
        language: Primary language of the project.
        structures_found: List of {type, location, usage} dicts.
        patterns_found: Optional list of {pattern, location} dicts.
        runtime_constraints: Optional list like ["max memory 512MB", "async/await"].

    Returns: {stored: true, project_id: "xxxx", validated: {known_patterns, known_structures, unknown}}
    """
    return _bootstrap_context(
        project_path=project_path,
        language=language,
        structures_found=_coerce(structures_found, list),
        patterns_found=_coerce(patterns_found, list),
        runtime_constraints=_coerce(runtime_constraints, list),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
