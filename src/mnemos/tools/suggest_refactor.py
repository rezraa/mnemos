# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: suggest_refactor — wired onto the Shape C retrieval engine (SEED-FROM-NODE).

suggest_refactor is the seed-from-node member of the four-step template the Coeus
tools and its Mnemos siblings (``plan_algorithm``, ``review_complexity``) inherit
(retrieve -> gate -> reason over own fields -> envelope). It DIVERGES at step one
only: those tools take the ``matched_signal_ids`` a caller recognised against
``get_signal_index``; suggest_refactor already HOLDS a known pattern id, so it SEEDS
retrieval from THAT pattern's OWN structural signals — ``kb.signal_ids_for(current_pattern)``
-> ONE ``kb.hydrate`` — with no forced signal-recognition step. hydrate's built-in
one-hop fan-out then expands the seed over the current pattern's ``alternatives``
edge, so the candidate set IS the related patterns the corpus records for it.

1. SEED + RETRIEVE — the current pattern's own signal ids drive one ``kb.hydrate``
   call — the proven four-state, fail-closed envelope; a pattern with no indexed
   signals (or an unknown id) abstains to EMPTY suggestions, never a husk. This
   replaces the retired exact-id ``get_alternatives`` + secondary ``get_structure``
   scan, whose flat 1.0/0.7 ``score`` was a tuned scalar with no retrieval signal
   behind it (the measured husk).
2. GATE — the shared ``_gate_and_rank`` with ``target_complexity`` folded in:
   complexity FEASIBILITY EXCLUDES every candidate whose OWN time/space exceeds the
   target (or the input-size guideline for ``n``), surfacing as ``filtered_out``;
   the problem-trait facet gate SINKS a candidate whose own ``avoid_when`` facet the
   caller's stated traits satisfy (kept, marked ``gated``); survivors re-rank
   faster-first when a size constraint governs. No tuned scalar.
3. REASON — the SHARED alternatives-fan-out (``_alternatives_fan_out``, the same
   primitive ``review_complexity`` drives): one suggestion per surviving candidate
   over its OWN fields (``_fit``), the current pattern excluded from its own
   alternatives, ``improvement`` annotated against the current complexity. Driven
   with ``only_better=True`` — the "only if actually better" rank the husk had is
   KEPT: a candidate that is not strictly faster than the current complexity is
   DROPPED, not merely left un-annotated.
4. ENVELOPE + MEMORY — the four-state envelope (retrieval_state/unmatched/dangling)
   over deep-frozen patterns; empirical memory KEPT unchanged (``get_corrections``
   for past refactors, ``check_regression`` on each suggestion, ``get_context`` for
   codebase context) as a pure side annotation that never re-orders or drops a
   suggestion — the tuned-scalar demotion path retired with the score.

OUTPUT CONTRACT (the tuned-scalar husk is gone; the new shape is asserted by the tool tests):
    current           the agent's own diagnosis, echoed
    suggestions       strictly-better candidates with own-field ``fit`` + ``retrieval`` votes + ``gated`` + ``improvement``
    filtered_out      candidates excluded by the complexity-feasibility / target gate
    retrieval_state   the hydrate envelope state (hit/low_confidence/no_match/dangling)
    unmatched         seeded signal ids the index did not recognise
    dangling          referenced pattern ids that did not resolve to a corpus pattern
    unknown_constraints  only when a constraints key is undeclared: {keys, declared}
    invalid_constraint_values  only when a declared key's value is not allowed (not
                      applied): {spelling: {value, reason, allowed | example}}
    context / memory  project codebase context + empirical-memory annotations (KEPT)
``constraints_analyzed`` echoes the bounded constraints (diagnostic artifact).

Firewall: imports only mnemos.* — never coeus.*/othrys.*.
"""

from __future__ import annotations

from typing import Any

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


def _refactor_memory(mem: Any, suggestions: list[dict], project_id: str | None) -> dict:
    """Empirical-memory annotations for a refactor — the store calls KEPT unchanged.

    ``get_corrections`` surfaces the project's last few recorded refactors
    (from/to/reason); ``check_regression`` flags any suggestion whose (pattern, ds)
    regressed before, keyed on (pattern_id, its parent structure = structure_id).
    Pure annotation: it never re-orders or drops a suggestion — the tuned-scalar
    demotion path retired with the score.
    """
    info: dict[str, Any] = {}
    if project_id:
        corrections = mem.get_corrections(project_id=project_id)
        if corrections:
            info["past_corrections"] = [
                {"from": c.original_pattern, "to": c.corrected_pattern, "reason": c.reason}
                for c in corrections[-3:]
            ]
    regressions: list[dict[str, Any]] = []
    for s in suggestions:
        pid = s.get("pattern_id", "")
        ds = s.get("structure_id", "")
        if pid and ds:
            reg = mem.check_regression(pattern=pid, ds=ds)
            if reg:
                regressions.append({
                    "pattern": pid,
                    "ds": ds,
                    "description": reg.description,
                    "severity": reg.severity.value,
                })
    if regressions:
        info["regressions_on_suggestions"] = regressions
    return info


def suggest_refactor(
    current_pattern: str | None = None,
    current_structure: str | None = None,
    current_complexity: str | None = None,
    target_complexity: str | None = None,
    constraints: dict | None = None,
    project_id: str | None = None,
    k: int = 10,
    conn: object = None,
) -> dict:
    """Suggest strictly-better refactoring alternatives to a known current pattern.

    SEED-FROM-NODE: retrieval is seeded from ``current_pattern``'s OWN structural
    signals (``kb.signal_ids_for`` -> ``kb.hydrate``), whose one-hop fan-out expands
    over that pattern's ``alternatives`` — the caller supplies no signal ids.

    CRITICAL INVARIANT (the gate + the rank): a candidate whose OWN complexity exceeds
    ``target_complexity`` (or the input-size guideline for ``n``) is EXCLUDED into
    ``filtered_out``; of the survivors, only those strictly FASTER than
    ``current_complexity`` are returned (the "only if actually better" rank), each
    annotated with its ``improvement`` delta. With no size constraint the hydrate vote
    order is preserved.

    Args:
        current_pattern: The pattern id the agent diagnosed — the seed node. Retrieval
            hydrates its OWN signals; it is excluded from its own alternatives. An
            unknown/absent id (or none) abstains to empty (fail closed).
        current_structure: The current data structure — echoed in ``current`` for the
            caller's reference (retrieval is seeded from the pattern, not this).
        current_complexity: The current time complexity, e.g. ``"O(n^2)"`` — the
            baseline each candidate must strictly beat to be suggested.
        target_complexity: The desired time complexity, e.g. ``"O(n)"`` — folded into
            the feasibility gate so a candidate exceeding it is excluded.
        constraints: Optional dict — ``n``/``input_size`` (int) drive the
            complexity-feasibility exclusion and the faster-first re-rank; ``space``
            adds a further exclusion. Bounded at the caller boundary.
        project_id: Optional project id for empirical-memory context (KEPT).
        k: Number of candidates to retrieve (engine-clamped to 1..50).
        conn: Kuzu/LadybugDB connection for graph mode, or None for JSON.

    Returns:
        The output contract (see the module docstring). Fail-closed: an abstaining
        envelope returns empty ``suggestions``/``filtered_out`` while context and
        memory still stand — never a husk.
    """
    # Fail-safe at the caller boundary: a malformed payload coerces cleanly rather
    # than raising (the server wrapper coerces JSON-string args; this guards the rest).
    constraints = _bounded_constraints(constraints if isinstance(constraints, dict) else {})
    # target_complexity folds into the gate constraints, so it is resolved and
    # reported with them.
    gate = dict(constraints)
    if target_complexity:
        gate["target_complexity"] = target_complexity
    gate_values, notices = _checked_constraints(gate)
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 10

    kb = get_knowledge(conn)
    mem = get_memory(conn)

    current: dict[str, Any] = {}
    if current_pattern:
        current["pattern"] = current_pattern
    if current_structure:
        current["structure"] = current_structure
    if current_complexity:
        current["complexity"] = current_complexity
    if target_complexity:
        current["target"] = target_complexity

    # Project context is candidate-independent — computed once, present on every path.
    context_info = _context_block(mem, project_id)

    # 1. SEED + RETRIEVE — the current pattern's OWN signal ids drive one hydrate call
    #    (seed-from-node); its one-hop fan-out expands over the pattern's
    #    ``alternatives`` edge. The caller-boundary cap is non-amplifying (the engine's
    #    _SEED_CAP already bounds fan-out downstream of it).
    seed_signal_ids = kb.signal_ids_for(current_pattern) if current_pattern else []
    res = kb.hydrate(seed_signal_ids[:_MAX_MATCHED_SIGNALS], k=k, constraints=gate_values)
    envelope = {
        "retrieval_state": res.state,
        "unmatched": list(res.unmatched_signals),
        "dangling": list(res.dangling),
        **notices,
    }

    # 2. Fail closed: an unknown/signal-less seed (no_match) or an unresolvable
    #    fan-out (dangling) abstains structurally — no suggestions, never a husk. The
    #    retrieval-independent context/memory still stand.
    if res.state in (NO_MATCH, DANGLING):
        result = {
            "current": current,
            "constraints_analyzed": constraints,
            "suggestions": [],
            "filtered_out": [],
            "context": context_info,
            "memory": _refactor_memory(mem, [], project_id),
            **envelope,
        }
        emit_event("suggest_refactor", {
            "current_pattern": current_pattern or "?",
            "current_complexity": current_complexity or "?",
            "target_complexity": target_complexity or "any",
            "state": res.state,
            "suggestions_count": 0,
        })
        return result

    # The seed IS the current pattern — the baseline, not a candidate. Drop it before
    # the gate so ``filtered_out`` reports only genuine alternatives, never the pattern
    # the caller is refactoring away from (which by definition exceeds the target).
    candidates = [p for p in res.patterns if p["id"] != current_pattern]

    # 3. GATE — _gate_and_rank with target_complexity folded into the constraints:
    #    complexity-feasibility EXCLUSION into filtered_out, the trait-facet SINK, then
    #    faster-first within each tier when a SIZE constraint governs; with none, the
    #    hydrate vote order is preserved.
    survivors, gated_ids, filtered_out = _gate_and_rank(kb, candidates, gate, gate_values)

    # 4. REASON — the shared alternatives-fan-out with only_better=True: the current
    #    pattern is excluded from its own alternatives, each surviving candidate is
    #    reasoned over its OWN fields (_fit), and ONLY the candidates strictly faster
    #    than the current complexity are kept (the "only if actually better" rank),
    #    each carrying its improvement delta.
    suggestions = _alternatives_fan_out(
        kb, survivors, gated_ids, current_complexity, current_pattern, only_better=True,
    )

    result = {
        "current": current,
        "constraints_analyzed": constraints,
        "suggestions": suggestions,
        "filtered_out": filtered_out,
        "context": context_info,
        "memory": _refactor_memory(mem, suggestions, project_id),
        **envelope,
    }

    emit_event("suggest_refactor", {
        "current_pattern": current_pattern or "?",
        "current_complexity": current_complexity or "?",
        "target_complexity": target_complexity or "any",
        "state": res.state,
        "suggestions_count": len(suggestions),
    })

    return result
