# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: plan_algorithm — wired onto the Shape C retrieval engine.

Mnemos's ``recommend_pattern``: the algorithm/data-structure decision tool, on the
same four-step template the Coeus tools inherit (retrieve → gate → reason over own
fields → envelope), diverging only where the domain demands it. Given the signal
ids the caller recognised against ``get_signal_index`` plus an optional constraints
dict, it:

1. RETRIEVES candidates through one ``kb.hydrate`` call — the proven four-state,
   fail-closed envelope; ``no_match``/``dangling`` abstain to empty recommendations,
   never a husk. This replaces the retired ``match_structural_signals`` substring
   pass, which returned EMPTY on problem-language (measured: 0/25 PB, 0/22 TK on the
   frozen benchmark) — the whole reason for the retrofit.
2. GATES through the shared ``_gate_and_rank``: complexity FEASIBILITY EXCLUDES
   every retrieved pattern whose OWN time/space complexity exceeds the caller's
   bounds (surfaced as ``filtered_out`` — the Mnemos-specific gate output Coeus's
   ``is_gated`` sink has no analogue for); the problem-trait facet gate SINKS a
   pattern whose own ``avoid_when`` facet the caller's stated traits satisfy
   (kept, marked ``gated``); survivors re-rank faster-first when a size constraint
   governs. Hydrate already broke equal-vote ties by ``use_when`` fit under the
   same traits. No tuned scalar.
3. REASONS fit over each retrieved pattern's OWN fields (``complexity`` /
   ``use_when`` / ``avoid_when`` / ``constraints``) — no decision-rule layer, no
   hardcoded table — and annotates known regressions from empirical memory
   (``check_regression``, unchanged). Empirical memory is a side annotation only: it
   NEVER re-orders the recommendations, so the ranking is memory-independent and the
   BAR-1 recall floor is reproducible regardless of the memory store's contents.

OUTPUT CONTRACT (matched_rules is gone; the new shape is asserted by the tool tests):
    recommendations   ranked candidates, each with its own-field ``fit``, ``retrieval`` votes
                      (incl. ``use_when_fit``) and ``gated`` (sunk by its own avoid_when facet)
    filtered_out      patterns excluded by the complexity-feasibility gate, with the reason
    retrieval_state   the hydrate envelope state (hit/low_confidence/no_match/dangling)
    unmatched         matched signal ids the index did not recognise
    dangling          referenced pattern ids that did not resolve to a corpus pattern
    unknown_constraints  only when a constraints key is undeclared: {keys, declared}
    invalid_constraint_values  only when a declared key's value is not allowed (not
                      applied): {spelling: {value, reason, allowed | example}}
    context / memory  project codebase context + empirical-memory annotations (kept)
Everything else on the surface (``constraints_analyzed`` echo, the emitted event) is
ARTIFACT — diagnostic, not part of the guarantee.

This retrofit STOPS the last *tool* caller of ``match_structural_signals`` (the only
remaining callers are the pinned baseline grader and the loader unit tests, both
retired at S6). Firewall: imports only mnemos.* — never coeus.*/othrys.*.
"""

from __future__ import annotations

from typing import Any

from mnemos.knowledge.loader import DANGLING, NO_MATCH
from mnemos.tools._shared import (
    _MAX_MATCHED_SIGNALS,
    _bounded_constraints,
    _checked_constraints,
    _fit,
    _gate_and_rank,
    emit_event,
    get_knowledge,
    get_memory,
)


def _project_context(mem: Any, project_id: str | None) -> dict:
    """Project codebase context (candidate-independent). Empirical memory, KEPT."""
    if not project_id:
        return {}
    ctx = mem.get_context(project_id)
    if not ctx:
        return {}
    return {
        "project_id": ctx.project_id,
        "structures_in_use": [s.type for s in ctx.structures_found],
        "patterns_in_use": [p.pattern for p in ctx.patterns_found],
        "runtime_constraints": ctx.runtime_constraints,
    }


def _memory_block(mem: Any, recommendations: list[dict], project_id: str | None) -> dict:
    """Empirical-memory annotations over the recommendations (``check_regression``,
    ``get_decisions`` — both KEPT, called exactly as before).

    A regression is keyed on (pattern_id, its parent structure = the ds). This is a
    pure annotation: it never re-orders or drops a recommendation.
    """
    info: dict[str, Any] = {}
    regressions: list[dict[str, Any]] = []
    for r in recommendations:
        pid = r.get("pattern_id", "")
        ds = r.get("structure_id", "")
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
        info["regressions"] = regressions
    if project_id:
        recent = mem.get_decisions(project_id=project_id)
        if recent:
            info["past_decisions"] = len(recent)
            info["last_pattern"] = recent[-1].pattern_chosen
    return info


def plan_algorithm(
    problem: str,
    matched_signal_ids: list[str],
    constraints: dict | None = None,
    project_id: str | None = None,
    k: int = 10,
    conn: object = None,
) -> dict:
    """Recommend algorithm + data structure for a problem's matched signals.

    CRITICAL INVARIANT (the gate): a pattern whose OWN complexity exceeds the
    input-size guideline for ``n`` is EXCLUDED from ``recommendations`` and surfaced
    in ``filtered_out`` — an O(n^2) candidate never survives for n=10^6 — while the
    survivors are re-ranked faster-first. With no size constraint the hydrate vote
    order is preserved (the retrieval-relevance signal governs).

    Args:
        problem: The problem's north-star sentence — context/telemetry only
            (retrieval is driven by ``matched_signal_ids``, not this text).
        matched_signal_ids: Signal ids the caller recognised against
            ``get_signal_index`` (problem-language → sig-id, the proven path). The
            retired ``structural_signals`` prose param has NO alias shim — its
            replacement is a different vocabulary.
        constraints: Optional dict — ``n``/``input_size`` (int) drive the
            complexity-feasibility exclusion; ``space``/``target_complexity`` add
            further exclusions. Bounded at the caller boundary.
        project_id: Optional project id for empirical-memory context (KEPT).
        k: Number of ranked candidates to retrieve (engine-clamped to 1..50).
        conn: Kuzu/LadybugDB connection for graph mode, or None for JSON.

    Returns:
        The output contract (see the module docstring): ``recommendations`` /
        ``filtered_out`` / ``retrieval_state`` / ``unmatched`` / ``dangling`` plus
        ``context`` / ``memory`` and the ``constraints_analyzed`` echo. Fail-closed:
        an abstaining envelope returns empty lists, never a husk.
    """
    # Fail-safe at the caller boundary: a malformed payload abstains cleanly rather
    # than raising (the server wrapper coerces JSON-string args; this guards the rest).
    matched_signal_ids = list(matched_signal_ids) if isinstance(matched_signal_ids, (list, tuple)) else []
    constraints = _bounded_constraints(constraints if isinstance(constraints, dict) else {})
    gate_values, notices = _checked_constraints(constraints)
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 10

    kb = get_knowledge(conn)
    mem = get_memory(conn)

    # 1. RETRIEVE — one hydrate call; the caller-boundary cap is non-amplifying
    #    (the engine's _SEED_CAP already bounds fan-out downstream of it).
    res = kb.hydrate(matched_signal_ids[:_MAX_MATCHED_SIGNALS], k=k, constraints=gate_values)
    envelope = {
        "retrieval_state": res.state,
        "unmatched": list(res.unmatched_signals),
        "dangling": list(res.dangling),
        **notices,
    }

    # Project context is candidate-independent — computed once, present on every path.
    context_info = _project_context(mem, project_id)

    # 2. Fail closed: recognised-but-empty (no_match) or unresolvable (dangling)
    #    abstains structurally — no recommendations, no filtered_out, never a husk.
    if res.state in (NO_MATCH, DANGLING):
        result = {
            "constraints_analyzed": constraints,
            "recommendations": [],
            "filtered_out": [],
            "context": context_info,
            "memory": _memory_block(mem, [], project_id),
            **envelope,
        }
        emit_event("plan_algorithm", {
            "problem": problem[:120] if isinstance(problem, str) else "",
            "n_signals": len(matched_signal_ids),
            "state": res.state,
            "recommendations_count": 0,
            "filtered_out_count": 0,
        })
        return result

    # 3. GATE — _gate_and_rank: complexity-feasibility EXCLUSION, the trait-facet
    #    SINK, then faster-first within each tier when a SIZE constraint governs. With
    #    no constraints the survivors keep hydrate's integer-vote order (so the BAR-1
    #    recall floor reproduces the engine exactly).
    survivors, gated_ids, filtered_out = _gate_and_rank(kb, res.patterns, constraints, gate_values)

    # 4. REASON — one recommendation per survivor over its OWN fields (_fit); resolve
    #    the parent structure as the data-structure (ds) the recommendation names.
    recommendations: list[dict[str, Any]] = []
    for rank, p in enumerate(survivors, start=1):
        pid = p["id"]
        parent = kb.get_pattern(pid)
        recommendations.append({
            "rank": rank,
            "pattern_id": pid,
            "pattern_name": p.get("name", pid),
            "structure_id": parent.get("structure_id", "") if parent else "",
            "fit": _fit(p),
            "retrieval": dict(p["retrieval"]),   # plain dict for the output surface
            "gated": pid in gated_ids,
        })

    result = {
        "constraints_analyzed": constraints,
        "recommendations": recommendations,
        "filtered_out": filtered_out,
        "context": context_info,
        "memory": _memory_block(mem, recommendations, project_id),
        **envelope,
    }

    emit_event("plan_algorithm", {
        "problem": problem[:120] if isinstance(problem, str) else "",
        "n_signals": len(matched_signal_ids),
        "state": res.state,
        "recommendations_count": len(recommendations),
        "filtered_out_count": len(filtered_out),
    })

    return result
