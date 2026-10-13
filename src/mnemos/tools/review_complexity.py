# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: review_complexity — wired onto the Shape C retrieval engine.

The agent has already read the code and reports what it detected (pattern,
structures, complexity). This tool, on the same four-step template the Coeus
tools and ``plan_algorithm`` inherit (retrieve -> gate -> reason over own fields
-> envelope), does two things the retired husk never did:

1. RETRIEVES candidate structures/algorithms through ONE ``kb.hydrate`` call — the
   proven four-state, fail-closed envelope; ``no_match``/``dangling`` abstain to
   EMPTY alternatives, never a husk. This replaces the old exact-id
   ``get_pattern``/``get_alternatives`` lookup, which returned NOTHING whenever the
   agent's ``detected_pattern`` was not a verbatim corpus id (the measured husk:
   ``{is_feasible: true}`` and empty ``alternatives``).
2. GATES the retrieved candidates through the shared ``_gate_and_rank``: complexity
   FEASIBILITY EXCLUDES every candidate whose OWN time/space complexity exceeds the
   caller's bounds (surfaces as ``filtered_out``); the problem-trait facet gate SINKS
   a candidate whose own ``avoid_when`` facet the caller's stated traits satisfy
   (kept, marked ``gated``); survivors re-rank faster-first when a size constraint
   governs. No tuned scalar.
3. REASONS over each candidate's OWN fields (``_fit``: complexity / use_when /
   avoid_when / constraints) and annotates ``improvement`` on the ones strictly
   faster than the agent's ``detected_complexity`` — the "better options". Separately
   it reasons the FEASIBILITY of the agent's OWN detected complexity against the
   constraints (its own complexity vs the input-size/space/target guidelines), so
   feasibility is now populated with a REASON on both the feasible and infeasible
   paths — killing the ``{is_feasible: true}``-and-nothing husk.

The detected echo (``detected_pattern``/``detected_structures``/``detected_complexity``/
``constraints``), the ``structure_info`` operation-cost lookup for the detected
structures, and the empirical-memory annotation (``check_regression`` on the
detected pattern, KEPT unchanged) are retrieval-INDEPENDENT and therefore present
on EVERY path, abstention included — an abstaining retrieval still returns an
honest review of what the agent detected, with no better options found.

OUTPUT CONTRACT (the husk is gone; the new shape is asserted by the tool tests):
    detected            the agent's own analysis, echoed
    feasibility         {is_feasible, reason} of the DETECTED complexity vs constraints
    alternatives        retrieved candidates (better options) with own-field ``fit`` and ``gated``
    filtered_out        candidates excluded by the complexity-feasibility gate
    structure_info      operation costs for the detected structures (KEPT)
    retrieval_state     the hydrate envelope state (hit/low_confidence/no_match/dangling)
    unmatched           matched signal ids the index did not recognise
    dangling            referenced pattern ids that did not resolve to a corpus pattern
    unknown_constraints only when a constraints key is undeclared: {keys, declared}
    invalid_constraint_values  only when a declared key's value is not allowed (not
                      applied): {spelling: {value, reason, allowed | example}}
    context / memory    project codebase context + empirical-memory annotations (KEPT)
``constraints_analyzed`` echoes the bounded constraints (diagnostic artifact).

Firewall: imports only mnemos.* — never coeus.*/othrys.*.
"""

from __future__ import annotations

from typing import Any, Mapping

from mnemos.knowledge.loader import DANGLING, NO_MATCH
from mnemos.tools._shared import (
    _MAX_MATCHED_SIGNALS,
    _alternatives_fan_out,
    _bounded_constraints,
    _checked_constraints,
    _context_block,
    _gate_and_rank,
    emit_event,
    get_knowledge,
    get_memory,
)


def _feasibility(kb: Any, detected_complexity: str | None, gate_values: Mapping[str, Any]) -> dict:
    """Reason the FEASIBILITY of the agent's OWN detected complexity against constraints.

    Runs the live Mnemos gate (:meth:`filter_by_constraints`) over a single dummy
    carrying the detected time complexity: if the gate removes it, the code is
    infeasible for the stated input size / space / target and the gate's own reason
    is surfaced; if it survives, it is feasible and the reason NAMES why (the
    input-size guideline it clears). With no gating constraint to test against, it is
    not flagged — is_feasible True with a reason that discloses the absence of a test.
    *gate_values* are the constraints as the gate resolves them, so an invalid value
    is never tested against. Populated {is_feasible, reason} on every path with a
    detected complexity — no tuned scalar, no hardcoded table (the guideline is
    data-driven from the corpus).
    """
    if not detected_complexity:
        return {}
    if not gate_values:
        return {
            "is_feasible": True,
            "reason": f"{detected_complexity} not flagged: no input-size/space/target "
                      f"constraint supplied to test against",
        }
    dummy = [{"id": "detected", "name": "detected", "complexity": {"time": detected_complexity}}]
    _surviving, removed = kb.filter_by_constraints(dummy, gate_values)
    if removed:
        return {"is_feasible": False, "reason": removed[0].get("filter_reason", "")}
    n = gate_values.get("n")
    if n is not None:
        return {"is_feasible": True,
                "reason": f"{detected_complexity} within the input-size guideline for n={n:,}"}
    return {"is_feasible": True, "reason": f"{detected_complexity} satisfies the given constraints"}


def _structure_info(kb: Any, detected_structures: list[str]) -> dict:
    """Operation costs + pattern count for each detected structure. KEPT unchanged:
    a data-driven lookup over the corpus structures the agent named."""
    info: dict[str, Any] = {}
    for sid in detected_structures:
        struct = kb.get_structure(sid)
        if struct:
            info[sid] = {
                "operations": struct.get("operations", {}),
                "pattern_count": len(struct.get("patterns", [])),
            }
    return info


def _detected_memory(kb: Any, mem: Any, detected_pattern: str | None) -> dict:
    """Empirical-memory annotation on the DETECTED pattern — ``check_regression``,
    KEPT unchanged. A regression is keyed on (detected_pattern, its parent
    structure = ds); the detected pattern is resolved to its ds via ``get_pattern``.
    Pure annotation: it never re-orders or drops an alternative."""
    if not detected_pattern:
        return {}
    parent = kb.get_pattern(detected_pattern)
    ds = parent.get("structure_id", "") if parent else ""
    if not ds:
        return {}
    reg = mem.check_regression(pattern=detected_pattern, ds=ds)
    if not reg:
        return {}
    return {"regressions": [{
        "pattern": detected_pattern,
        "ds": ds,
        "description": reg.description,
        "severity": reg.severity.value,
    }]}


def review_complexity(
    detected_pattern: str | None = None,
    detected_structures: list[str] | None = None,
    detected_complexity: str | None = None,
    matched_signal_ids: list[str] | None = None,
    constraints: dict | None = None,
    project_id: str | None = None,
    k: int = 10,
    conn: object = None,
) -> dict:
    """Review the agent's code analysis: is its complexity feasible, and are there
    better options?

    CRITICAL INVARIANT (the gate): a retrieved candidate whose OWN complexity exceeds
    the input-size guideline for ``n`` is EXCLUDED from ``alternatives`` and surfaced
    in ``filtered_out``; the survivors are re-ranked faster-first when a size
    constraint governs (with none, the hydrate vote order is preserved). Feasibility
    of the agent's OWN detected complexity is reasoned separately and is present on
    every path — the retrieval abstaining does NOT blank it.

    Args:
        detected_pattern: Pattern the agent identified (free text / corpus id). Echoed;
            used to key the empirical-memory regression check and excluded from its own
            alternatives. Retrieval is driven by ``matched_signal_ids``, not this.
        detected_structures: Structures the agent found, e.g. ``["array"]`` — echoed,
            and looked up for their operation costs (``structure_info``).
        detected_complexity: Complexity the agent estimated, e.g. ``"O(n^2)"`` — the
            "own" complexity whose feasibility is assessed and against which retrieved
            candidates are annotated as improvements.
        matched_signal_ids: Signal ids the caller recognised against
            ``get_signal_index``; the retrieval path that surfaces the better options.
        constraints: Optional dict — ``n``/``input_size`` (int) drive the
            complexity-feasibility exclusion and the feasibility verdict;
            ``space``/``target_complexity`` add further exclusions. Bounded at the
            caller boundary.
        project_id: Optional project id for empirical-memory context (KEPT).
        k: Number of candidates to retrieve (engine-clamped to 1..50).
        conn: Kuzu/LadybugDB connection for graph mode, or None for JSON.

    Returns:
        The output contract (see the module docstring). Fail-closed: an abstaining
        envelope returns empty ``alternatives``/``filtered_out`` while feasibility,
        structure_info, memory and context still stand — never a husk.
    """
    # Fail-safe at the caller boundary: malformed payloads coerce cleanly rather than
    # raise (the server wrapper coerces JSON-string args; this guards the rest).
    matched_signal_ids = list(matched_signal_ids) if isinstance(matched_signal_ids, (list, tuple)) else []
    detected_structures = list(detected_structures) if isinstance(detected_structures, (list, tuple)) else []
    constraints = _bounded_constraints(constraints if isinstance(constraints, dict) else {})
    gate_values, notices = _checked_constraints(constraints)
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 10

    kb = get_knowledge(conn)
    mem = get_memory(conn)

    detected: dict[str, Any] = {}
    if detected_pattern:
        detected["pattern"] = detected_pattern
    if detected_structures:
        detected["structures"] = detected_structures
    if detected_complexity:
        detected["complexity"] = detected_complexity

    # Retrieval-INDEPENDENT assessments — computed once, present on every path
    # (abstention included). Feasibility of the agent's OWN complexity, the detected
    # structures' operation costs, and empirical memory do not depend on retrieval.
    feasibility = _feasibility(kb, detected_complexity, gate_values)
    structure_info = _structure_info(kb, detected_structures)
    context_info = _context_block(mem, project_id)
    memory_info = _detected_memory(kb, mem, detected_pattern)

    # 1. RETRIEVE — one hydrate call; the caller-boundary cap is non-amplifying
    #    (the engine's _SEED_CAP already bounds fan-out downstream of it).
    res = kb.hydrate(matched_signal_ids[:_MAX_MATCHED_SIGNALS], k=k, constraints=gate_values)
    envelope = {
        "retrieval_state": res.state,
        "unmatched": list(res.unmatched_signals),
        "dangling": list(res.dangling),
        **notices,
    }

    # 2. Fail closed: recognised-but-empty (no_match) or unresolvable (dangling)
    #    abstains structurally — no alternatives, no filtered_out, never a husk. The
    #    retrieval-independent assessments above still stand.
    if res.state in (NO_MATCH, DANGLING):
        result = {
            "detected": detected,
            "constraints_analyzed": constraints,
            "feasibility": feasibility,
            "alternatives": [],
            "filtered_out": [],
            "structure_info": structure_info,
            "context": context_info,
            "memory": memory_info,
            **envelope,
        }
        emit_event("review_complexity", {
            "pattern": detected_pattern or "?",
            "complexity": detected_complexity or "?",
            "state": res.state,
            "alternatives_count": 0,
        })
        return result

    # 3. GATE — _gate_and_rank: complexity-feasibility EXCLUSION, the trait-facet
    #    SINK, then faster-first within each tier when a SIZE constraint governs. With
    #    no constraints the hydrate vote order is preserved.
    survivors, gated_ids, filtered_out = _gate_and_rank(kb, res.patterns, constraints, gate_values)

    # 4. REASON — the shared alternatives-fan-out (_alternatives_fan_out): one
    #    alternative per surviving candidate over its OWN fields (_fit), the detected
    #    pattern excluded from its own alternatives, ``improvement`` annotated when
    #    strictly faster than the detected complexity. review keeps every feasible
    #    survivor (only_better=False) and annotates the faster ones — the "better
    #    options"; suggest_refactor drives the SAME primitive with only_better=True.
    alternatives = _alternatives_fan_out(
        kb, survivors, gated_ids, detected_complexity, detected_pattern, only_better=False,
    )

    result = {
        "detected": detected,
        "constraints_analyzed": constraints,
        "feasibility": feasibility,
        "alternatives": alternatives,
        "filtered_out": filtered_out,
        "structure_info": structure_info,
        "context": context_info,
        "memory": memory_info,
        **envelope,
    }

    emit_event("review_complexity", {
        "pattern": detected_pattern or "?",
        "complexity": detected_complexity or "?",
        "state": res.state,
        "alternatives_count": len(alternatives),
    })

    return result
