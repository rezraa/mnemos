# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Shared state and utilities for all Mnemos MCP tools.

Every tool module imports from here to get access to the singleton
KnowledgeLoader / MemoryStore, the own-field candidate view (``_fit``), the shared
context block (``_context_block``), and the alternatives fan-out (``_alternatives_fan_out``).
"""

from __future__ import annotations

import functools
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from mnemos.knowledge.facet_catalogue_mirror import resolve_constraints, undeclared, validate_facets
from mnemos.knowledge.loader import FACET_CATALOGUE, KnowledgeLoader, _rank, is_gated, split_conditions
from mnemos.memory.store import MemoryStore

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singletons — shared across all tool modules
# ---------------------------------------------------------------------------

knowledge: KnowledgeLoader = KnowledgeLoader()
memory: MemoryStore = MemoryStore()

# Every corpus facet is validated against the catalogue at import, so an invalid
# catalogue or facet stops the server from starting rather than silently never
# matching.
validate_facets(FACET_CATALOGUE, knowledge.get_all_patterns())


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
# Caller-boundary ceilings — one source of truth, shared by every Shape-C tool
# ---------------------------------------------------------------------------
# A JUSTIFIED MIRROR of coeus.tools._shared (coeus _shared.py:220-236). The
# retrieval engine bounds its own fan-out (loader._SEED_CAP / _TOPK_CAP); these
# bound the UNTRUSTED caller input BEFORE that engine is reached, applied where
# the cost is incurred. Declared once here so a second tool cannot drift a second
# copy. The S3-S5 tool retrofits (plan_algorithm et al. moving onto hydrate) apply
# _MAX_MATCHED_SIGNALS before calling loader.hydrate(); get_signal_index is a
# read-only accessor with no unbounded caller input, so it needs none.
_MAX_MATCHED_SIGNALS = 256      # cap on caller-supplied signal ids, bound BEFORE hydrate
_MAX_CONSTRAINTS = 64           # cap on constraint-dict cardinality
_MAX_CONSTRAINT_VALUE_LEN = 256  # cap on each constraint value used in comparison
_MAX_DESCRIPTION_LEN = 4096     # cap on free-text description (context/telemetry only)


def _bounded_constraints(constraints: dict) -> dict:
    """Bound an untrusted constraints dict at the caller boundary.

    Keeps at most ``_MAX_CONSTRAINTS`` entries and clips each string value to
    ``_MAX_CONSTRAINT_VALUE_LEN`` characters so an unbounded dict cannot amplify
    the per-facet comparison cost. Pure sanitisation -- never interpretation.
    """
    bounded: dict[str, Any] = {}
    for key, val in list(constraints.items())[:_MAX_CONSTRAINTS]:
        bounded[key] = val[:_MAX_CONSTRAINT_VALUE_LEN] if isinstance(val, str) else val
    return bounded


def _checked_constraints(constraints: dict) -> tuple[Any, dict]:
    """Resolve caller constraints against the facet catalogue: ``(values, notices)``.

    ``values`` maps each declared key to the canonical value the gate
    (``filter_by_constraints``) reads, so a tool's own reading of a constraint agrees
    with the gate's. ``notices`` is merged into the envelope: ``unknown_constraints``
    for a key the catalogue does not declare (a misspelling such as ``max_space`` or
    ``N`` filters nothing) and ``invalid_constraint_values`` for a declared key whose
    value it does not allow (never applied). Both are absent when there is nothing to
    report, so a clean call's result is unchanged. Keys are echoed as clipped
    strings: a caller key is untrusted and may be any hashable."""
    resolved = resolve_constraints(FACET_CATALOGUE, constraints)
    notices: dict[str, Any] = {}
    keys = undeclared(FACET_CATALOGUE, constraints)
    if keys:
        notices["unknown_constraints"] = {
            "keys": sorted(str(k)[:_MAX_CONSTRAINT_VALUE_LEN] for k in keys),
            "declared": sorted(FACET_CATALOGUE.names),
        }
    if resolved.invalid:
        notices["invalid_constraint_values"] = {name: dict(report) for name, report in resolved.invalid.items()}
    return resolved.values, notices


# ---------------------------------------------------------------------------
# Gate + rank — the one ordering every Shape-C tool applies after hydrate
# ---------------------------------------------------------------------------

def _gate_and_rank(
    kb: Any, patterns: list[dict], gate: dict, gate_values: Any,
) -> tuple[list[dict], set[str], list[dict]]:
    """Order hydrated candidates for output: ``(survivors, gated_ids, filtered_out)``.

    Two gates over each pattern's OWN fields, in one place for all three tools:

    * EXCLUDE — ``kb.filter_by_constraints`` drops a candidate whose own complexity
      exceeds the caller's size / space / time bounds into ``filtered_out``.
    * SINK — a survivor whose own ``avoid_when`` facet the caller's resolved traits
      satisfy (:func:`is_gated`) is kept but ranked below every ungated one, and its
      id is returned in ``gated_ids``.

    Within each tier, a size constraint re-ranks faster-first; otherwise the hydrate
    order stands (votes, then ``use_when`` fit). The key ``(gated, complexity rank,
    hydrate index)`` is a total order over integers, so the result is
    byte-reproducible; with no traits every flag is ``False`` and the order is
    exactly the pre-sink order.
    """
    if gate:
        survivors, removed = kb.filter_by_constraints(list(patterns), gate)
    else:
        survivors, removed = list(patterns), []

    gated = [is_gated(p, gate_values) for p in survivors]
    by_size = "n" in gate_values

    def key(i: int) -> tuple[bool, int, int]:
        speed = _rank((survivors[i].get("complexity") or {}).get("time", "")) if by_size else 0
        return (gated[i], speed, i)

    order = sorted(range(len(survivors)), key=key)
    filtered_out = [
        {
            "pattern_id": r.get("id", ""),
            "pattern_name": r.get("name", r.get("id", "")),
            "complexity": dict(r.get("complexity") or {}),
            "reason": r.get("filter_reason", ""),
        }
        for r in removed
    ]
    gated_ids = {survivors[i]["id"] for i in range(len(survivors)) if gated[i]}
    return [survivors[i] for i in order], gated_ids, filtered_out


# ---------------------------------------------------------------------------
# Own-field candidate view — the one source of truth for "reason over a
# retrieved pattern's OWN fields", shared by every Shape-C tool retrofit.
# ---------------------------------------------------------------------------

def _fit(pattern: dict) -> dict:
    """Derive the fit view from a retrieved pattern's OWN fields — one source of truth.

    ``complexity`` / ``use_when`` / ``avoid_when`` / ``constraints`` are the
    corpus pattern's own data, so every recommendation or alternative carries its
    real tradeoff surface (no hardcoded detector, no fabricated score).
    ``split_conditions`` partitions the text conditions from the problem-trait facet
    dicts so a facet never leaks into the prose lists. Fresh copies are
    returned: the source pattern is deep-frozen at the hydrate boundary, so reading
    its fields is corpus-safe and the returned view is plainly mutable/JSON-safe.
    """
    use_texts, _ = split_conditions(pattern.get("use_when"))
    avoid_texts, _ = split_conditions(pattern.get("avoid_when"))
    return {
        "complexity": dict(pattern.get("complexity") or {}),
        "use_when": list(use_texts),
        "avoid_when": list(avoid_texts),
        "constraints": pattern.get("constraints", ""),
    }


def _context_block(mem: Any, project_id: str | None) -> dict:
    """Project codebase context (candidate-independent) — the one shared empirical-
    memory context block for the retrofit-wave tools.

    Lean shape: the project id and its runtime constraints, read from the memory
    store. One source of truth so review_complexity and suggest_refactor do not each
    carry a copy (empirical memory is KEPT; only the duplication is removed). Present
    on every path, abstention included — it is retrieval-independent.
    """
    if not project_id:
        return {}
    ctx = mem.get_context(project_id)
    if not ctx:
        return {}
    return {"project_id": ctx.project_id, "runtime_constraints": ctx.runtime_constraints}


# ---------------------------------------------------------------------------
# Alternatives fan-out — the one source of truth for "reason one alternative per
# surviving candidate over its OWN fields", shared by review_complexity and
# suggest_refactor (the dedupe S4 deferred to S5).
# ---------------------------------------------------------------------------

def _alternatives_fan_out(
    kb: Any,
    survivors: list[dict],
    gated_ids: set[str],
    baseline_complexity: str | None,
    exclude_id: str | None,
    only_better: bool = False,
) -> list[dict[str, Any]]:
    """Turn post-gate hydrated survivors into the ranked ``alternatives`` list.

    The REASON step of the four-step template — one entry per surviving candidate,
    reasoned over the candidate's OWN corpus fields, shared verbatim by
    review_complexity and suggest_refactor so the fan-out lives in exactly one place
    (grep-provable: this is its only definition). Each entry is
    ``{rank, pattern_id, pattern_name, structure_id, fit, retrieval, gated[, improvement]}``:
    own-field ``fit`` (:func:`_fit`), the integer-vote ``retrieval`` as a plain dict,
    the parent structure resolved as ``structure_id``, and ``gated`` from
    :func:`_gate_and_rank`'s ``gated_ids``. The candidate carrying
    ``exclude_id`` is dropped -- a pattern is never its own alternative.
    ``improvement`` is annotated whenever the candidate's OWN time complexity is
    strictly faster than ``baseline_complexity`` (the delta path).

    ``only_better`` is the two callers' one behavioural difference: review keeps every
    feasible survivor and annotates only the faster ones (the better options among all
    feasible candidates); refactor keeps ONLY the strictly-faster ones (the "only if
    actually better" rank). Ranks are assigned 1..N AFTER the drop, so they stay
    contiguous either way. No tuned scalar -- ordering is inherited from ``survivors``
    (the :func:`_gate_and_rank` order the caller already fixed).
    """
    baseline_rank = _rank(baseline_complexity) if baseline_complexity else None
    alternatives: list[dict[str, Any]] = []
    for p in survivors:
        pid = p["id"]
        if exclude_id and pid == exclude_id:
            continue
        fit = _fit(p)
        alt_time = fit["complexity"].get("time", "")
        is_better = (
            baseline_rank is not None and bool(alt_time)
            and _rank(alt_time) < baseline_rank
        )
        if only_better and not is_better:
            continue
        parent = kb.get_pattern(pid)
        alt: dict[str, Any] = {
            "rank": len(alternatives) + 1,
            "pattern_id": pid,
            "pattern_name": p.get("name", pid),
            "structure_id": parent.get("structure_id", "") if parent else "",
            "fit": fit,
            "retrieval": dict(p["retrieval"]),   # plain dict for the output surface
            "gated": pid in gated_ids,
        }
        if is_better:
            alt["improvement"] = f"{baseline_complexity} -> {alt_time}"
        alternatives.append(alt)
    return alternatives


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
# Kwarg normalisation — per-tool alias / ignore tables
# ---------------------------------------------------------------------------

def normalize_kwargs(func: Callable) -> Callable:
    """Remap caller kwarg synonyms to canonical params before invocation.

    Reads ``_ALIASES`` (synonym -> canonical) and ``_IGNORED`` (drop+warn)
    from the wrapped function's own module. Genuinely-unknown kwargs are
    left untouched so the wrapped signature still raises the standard
    ``unexpected keyword argument`` TypeError — typos are not swallowed.

    Raises TypeError if a synonym and its canonical (or two synonyms of the
    same canonical) are both supplied: an aliasing collision is ambiguous
    and must fail loud, not silently pick a winner.

    The tables are read from ``func.__globals__`` (not via module import) so
    this works both as a normal package import and inside the Othrys
    served-source sandbox, where each tool is exec'd into a synthetic
    namespace that is not importable by name.
    """
    g = func.__globals__
    aliases: dict[str, str] = g.get("_ALIASES", {})
    ignored: set[str] = g.get("_IGNORED", set())

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for name in list(kwargs):
            if name in ignored:
                _log.warning(
                    "%s: ignoring unsupported argument '%s'",
                    func.__name__, name,
                )
                kwargs.pop(name)
        remapped: dict[str, Any] = {}
        for name in list(kwargs):
            canonical = aliases.get(name)
            if canonical is None:
                continue
            value = kwargs.pop(name)
            if canonical in kwargs or canonical in remapped:
                raise TypeError(
                    f"{func.__name__}() received conflicting arguments for "
                    f"'{canonical}': both it and alias '{name}' were supplied"
                )
            remapped[canonical] = value
        kwargs.update(remapped)
        return func(*args, **kwargs)

    return wrapper
