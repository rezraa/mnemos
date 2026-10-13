# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Mnemos MCP Server — Algorithmic Reasoning Memory for LLMs.

Uses FastMCP's decorator-based tool registration to expose six tools:

    plan_algorithm      — recommend algorithm + DS for agent-identified signals
    review_complexity   — assess feasibility of agent-detected complexity
    suggest_refactor    — suggest alternatives given agent's diagnosis
    log_decision        — log an algorithmic decision to memory
    bootstrap_context   — store codebase context for project-aware recommendations
    get_signal_index    — deterministic Shape-C signal index (problem-language retrieval)
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
from mnemos.tools.get_signal_index import get_signal_index as _get_signal_index

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
    matched_signal_ids: Union[list[str], str],
    constraints: Union[dict, str, None] = None,
    project_id: str | None = None,
    k: int = 10,
) -> dict:
    """Recommend algorithm + DS for a problem's matched signals via the Shape-C engine.

    The agent recognises the problem's structural signals against ``get_signal_index``
    and passes their ids here. This tool hydrates them into ranked algorithm/DS
    candidates, EXCLUDES the complexity-infeasible ones for the given input size, and
    reasons fit over each candidate's own fields. The prose ``structural_signals``
    param is retired (no alias shim): its replacement is a different vocabulary.

    Args:
        problem: The problem's north-star sentence (context/telemetry only).
        matched_signal_ids: Signal ids recognised against get_signal_index.
        constraints: Optional dict — n/input_size drive the feasibility exclusion;
            space/target_complexity add further exclusions; problem traits (updates, arrival, input_order, query_shape, exactness,
            value_sign, graph_direction, graph_weighting) reorder candidates their
            own facets favour or avoid; allowed values are the facet catalogue's.
        project_id: Optional project ID for empirical-memory context.
        k: Number of ranked candidates to retrieve (engine-clamped to 1..50).

    Returns tight JSON: recommendations[], filtered_out[], retrieval_state,
    unmatched[], dangling[], context{}, memory{}, constraints_analyzed{}.
    """
    return _plan_algorithm(
        problem,
        matched_signal_ids=_coerce(matched_signal_ids, list),
        constraints=_coerce(constraints, dict),
        project_id=project_id,
        k=k,
    )


@mcp.tool()
def review_complexity(
    detected_pattern: str | None = None,
    detected_structures: Union[list[str], str, None] = None,
    detected_complexity: str | None = None,
    matched_signal_ids: Union[list[str], str, None] = None,
    constraints: Union[dict, str, None] = None,
    project_id: str | None = None,
    k: int = 10,
) -> dict:
    """Review complexity based on the agent's analysis of code, via the Shape-C engine.

    The agent reads the code, identifies the pattern and estimates complexity, and
    recognises the problem's structural signals against ``get_signal_index``. This
    tool reasons the FEASIBILITY of the detected complexity against constraints and
    hydrates the recognised signals into candidate structures/algorithms — surfacing
    the complexity-feasible BETTER OPTIONS (excluding the infeasible ones into
    filtered_out) and checking empirical memory for regressions.

    Args:
        detected_pattern: Pattern the agent found, e.g. "nested-loop".
        detected_structures: Structures the agent found, e.g. ["array"].
        detected_complexity: Complexity the agent estimated, e.g. "O(n^2)".
        matched_signal_ids: Signal ids recognised against get_signal_index (drives
            the retrieval of better options).
        constraints: Optional dict with keys like n, input_size, space, target_complexity;
            problem traits (updates, arrival, input_order, query_shape, exactness,
            value_sign, graph_direction, graph_weighting) reorder candidates their
            own facets favour or avoid; allowed values are the facet catalogue's.
        project_id: Optional project ID for codebase context.
        k: Number of candidates to retrieve (engine-clamped to 1..50).

    Returns tight JSON: detected{}, feasibility{}, alternatives[], filtered_out[],
    structure_info{}, retrieval_state, unmatched[], dangling[], context{}, memory{},
    constraints_analyzed{}.
    """
    return _review_complexity(
        detected_pattern=detected_pattern,
        detected_structures=_coerce(detected_structures, list),
        detected_complexity=detected_complexity,
        matched_signal_ids=_coerce(matched_signal_ids, list),
        constraints=_coerce(constraints, dict),
        project_id=project_id,
        k=k,
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
        constraints: Optional dict with keys like n, input_size, space;
            problem traits (updates, arrival, input_order, query_shape, exactness,
            value_sign, graph_direction, graph_weighting) reorder candidates their
            own facets favour or avoid; allowed values are the facet catalogue's.
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


@mcp.tool()
def get_signal_index() -> dict:
    """Return the deterministic Shape-C signal index for problem-language retrieval.

    Read-only, in the uniform nested container (one corpus-named group; a future
    corpus is a new group behind this same tool). Signals are keyed by their owning
    pattern; a signal owned by several patterns appears under each. The agent
    recognises a problem's structural signals against this view and passes the
    matched signal ids as matched_signal_ids to plan_algorithm / review_complexity.
    Sorted + byte-stable.

    Returns: {pattern_signals: {pattern_id: {signal_id: signal_text}}}
    """
    return _get_signal_index()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
