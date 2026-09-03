# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Knowledge loader for Mnemos-MCP.

Loads structures.json and complexities.json and provides pure retrieval, the
Shape-C signal-index hydrate engine (the sole retrieval path), and constraint
filtering (data-driven from complexities.json).

No fuzzy keyword matching.  No tokenization.  No Jaccard scoring.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path

_KNOWLEDGE_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Complexity ranking — lower index = faster.
# ---------------------------------------------------------------------------
_COMPLEXITY_RANK: list[str] = [
    "O(1)",
    "O(log n)",
    "O(sqrt(n))",
    "O(n)",
    "O(n log n)",
    "O(n * sqrt(n))",
    "O(n^2)",
    "O(n^2 log n)",
    "O(n^3)",
    "O(2^n)",
    "O(n!)",
    "O(n^n)",
]


# Aliases for complexity strings not in the main rank list.
_COMPLEXITY_ALIASES: dict[str, str] = {
    "O(V+E)": "O(n)",           # graph traversal ~ linear in input size
    "O(V * E^2)": "O(n^3)",     # e.g. Edmonds-Karp
    "O(V^2)": "O(n^2)",
    "O(V^3)": "O(n^3)",
    "O(n*m)": "O(n^2)",         # two-dimensional ~ quadratic
    "O(n*S)": "O(n^2)",         # knapsack-like
    "O(m*n)": "O(n^2)",
    "O(alpha(n))": "O(1)",      # inverse Ackermann ~ constant
    "O((V+E) log V)": "O(n log n)",  # Dijkstra
}


def _rank(complexity_str: str) -> int:
    """Return an integer rank for a complexity string.  Lower is faster.

    Handles common variations like 'O(n) build, O(1) query' by taking the
    dominant (worst) component, and 'O(1) amortized' by stripping qualifiers.
    """
    import re

    parts = complexity_str.split(",")
    canonical = parts[0].strip()
    canonical = re.sub(
        r"\s*(amortized|average|worst|expected|total|per query|per operation|build).*",
        "", canonical, flags=re.I,
    ).strip()
    try:
        return _COMPLEXITY_RANK.index(canonical)
    except ValueError:
        # Check aliases
        alias = _COMPLEXITY_ALIASES.get(canonical)
        if alias:
            return _COMPLEXITY_RANK.index(alias)
        if "log" in canonical:
            return _COMPLEXITY_RANK.index("O(n log n)")
        # Default to O(n) tier for unknowns (middle-of-road, not worst)
        return _COMPLEXITY_RANK.index("O(n)")


# ==========================================================================
# Shape-C retrieval engine — the signal-index hydrate path
# (problem-language signals -> pattern), a JUSTIFIED MIRROR of Coeus's engine
# (coeus.knowledge.loader, story-19e9ceb1). Mnemos runtime code never imports
# coeus.*/othrys.* (the decoupling firewall); the mirror is kept faithful by a
# semantic-parity drift test (tests/test_knowledge/test_firewall.py). Adapted
# for the Mnemos corpus shape: the index is built from each pattern's
# ``structural_signals`` (Coeus: ``signals``); the fan-out edge is
# ``alternatives`` (Coeus: ``related_patterns``); and ``self._pattern_index``
# stores ``(structure_id, pattern)`` tuples, so the index build and
# ``_lookup_pattern`` unwrap the tuple (Coeus's ``_all_patterns`` is a flat list).
# ==========================================================================
#
# The four-state retrieval envelope is the single output contract. Every
# retrieval resolves to exactly one state, and abstention is a structural field
# rather than an empty list narrated as an answer (fail closed, never a husk).
HIT = "hit"                        # >=1 pattern hydrated at/above the confidence floor
LOW_CONFIDENCE = "low_confidence"  # patterns hydrated, best below the confidence floor
NO_MATCH = "no_match"              # signals recognised but none map to a corpus pattern
DANGLING = "dangling"              # signals map only to ids absent from the corpus

# Two named ceilings bound the fan-out's agency, applied where cost is incurred:
_SEED_CAP: int = 64    # max seed patterns admitted to fan-out (bound BEFORE expansion)
_TOPK_CAP: int = 50    # hard ceiling on hydrated results (bound AFTER expansion)

# A hit needs at least this many corroborating votes (direct + propagated); a
# lone single vote is surfaced but flagged low_confidence. Auditable integer,
# not a tuned score.
_CONFIDENCE_FLOOR: int = 2


def _signal_id(text: str) -> str:
    """Deterministic, byte-reproducible id for a signal's text.

    A stable content hash so the corpus-derived index recomputes identically
    across processes (independent of PYTHONHASHSEED) and the LLM/harness can
    refer to a signal by a short id.
    """
    return "sig-" + hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class RetrievalResult:
    """The single retrieval output contract (see the four states above).

    ``patterns`` is the ranked, hydrated result (empty for the abstention
    states). ``votes`` is the transparent, auditable tally used for ranking
    (pattern_id -> integer vote count). ``dangling`` surfaces any referenced
    pattern id that did not resolve to a corpus pattern -- an integrity failure
    is reported, never masked by a husk. ``unmatched_signals`` records matched
    signal ids the index did not recognise.
    """

    state: str
    patterns: list[dict] = field(default_factory=list)
    votes: dict[str, int] = field(default_factory=dict)
    dangling: list[str] = field(default_factory=list)
    unmatched_signals: list[str] = field(default_factory=list)
    reason: str = ""


class _FrozenDict(dict):
    """A read-only ``dict``: refuses in-place mutation, serialises as a plain dict.

    Hydrated patterns are deep-frozen through this type so a caller cannot corrupt
    the shared singleton corpus by mutating a returned pattern (the shallow-copy
    shared-reference hazard: ``{**pat}`` copies the top dict but aliases its nested
    lists). It subclasses ``dict`` so ``json.dumps`` and ``["key"]`` reads work
    unchanged; only the mutators are sealed.
    """

    __slots__ = ()

    def _readonly(self, *_a: object, **_k: object) -> None:
        raise TypeError("hydrated pattern is read-only")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _readonly


def deep_freeze(obj: object) -> object:
    """Recursively copy *obj* into an immutable, JSON-serialisable structure.

    Dicts become :class:`_FrozenDict`, lists/tuples become tuples, scalars pass
    through. The copy severs every shared reference to the source, so this both
    fixes the shared-ref corruption hazard and makes the result tamper-proof.
    """
    if isinstance(obj, dict):
        return _FrozenDict({k: deep_freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(deep_freeze(v) for v in obj)
    return obj


def _parse_team_range(token: object) -> tuple[float, float] | None:
    """Parse a ``team_size`` token (``"1-5"``, ``"50+"``, ``"3"``) into ``(lo, hi)``.

    Pure string arithmetic -- no regex, no eval on caller input. Returns ``None``
    for anything unparseable so the gate can fail OPEN (never demote on a token it
    cannot read). Ported from Coeus as part of the facet gate; DORMANT on the
    Mnemos corpus (no pattern carries facet dicts in its ``avoid_when``), but kept
    faithful so the semantic-parity drift test holds and S3-S5 tool retrofits have
    the primitive ready.
    """
    s = str(token).strip()
    if not s:
        return None
    try:
        if s.endswith("+"):
            return (int(s[:-1]), float("inf"))
        if "-" in s:
            lo, hi = s.split("-", 1)
            return (int(lo), int(hi))
        n = int(s)
        return (n, n)
    except (ValueError, TypeError):
        return None


def facet_matches(facet: dict, constraints: dict) -> bool:
    """Does one structured facet hold under the caller's *constraints*?

    The single facet-matching predicate (one source of truth, not one copy per
    reader). A facet is an AND of conditions; it matches only when the constraints
    confirm *every* key: ``team_size`` by numeric range overlap, every other key by
    categorical exact match (case/whitespace-normalised, never substring). Pure
    comparison -- no ``eval``/regex on caller input; an unspecified or unreadable
    key yields ``False`` (fail open, never demote on unconfirmed input). Ported
    from Coeus; DORMANT on the Mnemos corpus (facet gate ready for S3-S5).
    """
    if not isinstance(facet, dict) or not facet:
        return False
    for key, fval in facet.items():
        cval = constraints.get(key)
        if cval is None:
            return False
        if key == "team_size":
            fr, cr = _parse_team_range(fval), _parse_team_range(cval)
            if fr is None or cr is None:
                return False
            if not (fr[0] <= cr[1] and cr[0] <= fr[1]):
                return False
        elif str(cval).strip().lower() != str(fval).strip().lower():
            return False
    return True


def split_conditions(items: list | None) -> tuple[list[str], list[dict]]:
    """Partition a ``use_when``/``avoid_when`` list into its two kinds.

    These lists mix free-text condition strings (for LLM recognition) and
    structured facet dicts (for deterministic gating). Any reader dispatches on
    element type through this one helper. Single pass; tolerates ``None``. Returns
    ``(text_conditions, facet_constraints)``. Ported from Coeus; on the Mnemos
    corpus the facet half is always empty (DORMANT).
    """
    texts: list[str] = []
    facets: list[dict] = []
    for item in items or []:
        (facets if isinstance(item, dict) else texts).append(item)
    return texts, facets


def is_gated(pattern: dict, constraints: dict) -> bool:
    """Is *pattern* gated by its OWN ``avoid_when`` facets under *constraints*?

    Reasoning over the pattern's own field, not a hardcoded detector. Ported from
    Coeus as the deterministic facet gate; DORMANT on the Mnemos corpus (no
    pattern carries an ``avoid_when`` facet dict), so it always returns ``False``
    here. The complexity gate that IS live on Mnemos is
    :meth:`KnowledgeLoader.filter_by_constraints` (input-size feasibility).
    """
    if not constraints:
        return False
    _, facets = split_conditions(pattern.get("avoid_when"))
    return any(facet_matches(f, constraints) for f in facets)


class _SignalEngine:
    """The Shape-C signal-index retrieval engine, inherited by BOTH loaders.

    One engine, both modes: :class:`KnowledgeLoader` (JSON) and
    ``GraphKnowledgeLoader`` (Kuzu) each build the shared ``self._pattern_index``
    (``pattern_id -> (structure_id, pattern)``) in ``__init__`` and then call
    :meth:`_build_signal_index`; every method below reads only that shared
    attribute, so there is exactly ONE copy of the engine (no duplicate engine
    code across the two loaders).
    """

    # ------------------------------------------------------------------
    # Index build (called from each loader's __init__, after _pattern_index)
    # ------------------------------------------------------------------

    def _build_signal_index(self) -> None:
        """Build ``self._signal_index`` from each pattern's ``structural_signals``.

        Derived deterministically so the view is byte-reproducible (ids are
        content hashes; pattern_ids sorted). Fails CLOSED at load on a hash
        collision between two distinct signal texts -- a 48-bit clash would
        silently merge two signals, so we refuse to serve a corrupted index
        rather than mask it. ``self._pattern_index`` stores ``(structure_id,
        pattern)`` tuples (the Mnemos shape); the tuple is unwrapped here.
        """
        self._signal_index: dict[str, dict] = {}
        for _structure_id, pattern in self._pattern_index.values():
            pid = pattern["id"]
            for raw in pattern.get("structural_signals", []):
                text = raw.strip()
                if not text:
                    continue
                sid = _signal_id(text)
                entry = self._signal_index.get(sid)
                if entry is None:
                    self._signal_index[sid] = {
                        "signal_id": sid,
                        "signal_text": text,
                        "pattern_ids": [pid],
                    }
                elif entry["signal_text"] != text:
                    raise ValueError(
                        f"signal_id collision {sid}: "
                        f"{text!r} vs {entry['signal_text']!r}"
                    )
                elif pid not in entry["pattern_ids"]:
                    entry["pattern_ids"].append(pid)
        for entry in self._signal_index.values():
            entry["pattern_ids"].sort()

    # ------------------------------------------------------------------
    # Pattern-id resolution (retrieval engine)
    # ------------------------------------------------------------------

    def _lookup_pattern(self, pattern_id: str) -> dict | None:
        """Resolve a pattern id to its stored dict, fail closed.

        Returns the real pattern dict or ``None`` -- never a synthesised
        ``{id, name}`` husk. Unwraps the ``(structure_id, pattern)`` tuple that
        ``self._pattern_index`` stores; the retrieval engine records a ``None``
        as a typed ``dangling`` reference in the envelope.
        """
        entry = self._pattern_index.get(pattern_id)
        if entry is None:
            return None
        return entry[1]

    # ------------------------------------------------------------------
    # Signal-index retrieval engine (problem-language -> pattern)
    # ------------------------------------------------------------------

    def get_signal_index(self) -> list[dict]:
        """Return the deterministic, byte-reproducible signal index view.

        Each entry is ``{signal_id, signal_text, pattern_ids}``; the LLM
        recognises a problem's signals against this view at runtime and passes
        the matched signal ids to :meth:`hydrate`. Sorted by ``signal_id`` with
        sorted ``pattern_ids`` so two builds serialise identically.
        """
        return [
            {
                "signal_id": e["signal_id"],
                "signal_text": e["signal_text"],
                "pattern_ids": list(e["pattern_ids"]),
            }
            for e in sorted(self._signal_index.values(), key=lambda e: e["signal_id"])
        ]

    def signal_ids_for(self, pattern_id: str) -> list[str]:
        """Return the signal ids of *pattern_id*'s OWN structural signals.

        The seed-from-node entry point: a tool that already HOLDS a known pattern id
        (``suggest_refactor``) recovers that pattern's own signal ids from the built
        index -- exactly the ids :meth:`hydrate` recognises -- and seeds the retrieval
        with them, so the fan-out expands over the pattern's ``alternatives`` without a
        caller-supplied signal-recognition step. Reads only the shared
        ``self._signal_index`` (the one source of truth for text -> signal id), so the
        JSON and graph loaders derive the IDENTICAL seed; sorted for a deterministic,
        byte-reproducible order. An unknown or signal-less id yields ``[]`` (the caller
        then hydrates to a fail-closed ``no_match``), never a fabricated seed.
        """
        return sorted(
            sid for sid, entry in self._signal_index.items()
            if pattern_id in entry["pattern_ids"]
        )

    def hydrate(
        self,
        matched_signal_ids: list[str],
        k: int = 10,
        fan_out: bool = True,
    ) -> RetrievalResult:
        """Hydrate matched signals into ranked patterns, in the four-state envelope.

        End-to-end entry point a harness drives given matched signal ids:

        * maps each signal id -> its owning pattern(s), tallying a direct vote
          per signal (a seed's weight = number of matched signals mapping to it);
        * one-hop fan-out over ``alternatives`` from the capped seed set,
          propagating each seed's weight to its neighbours (when ``fan_out``);
        * selects the top-``k`` via a size-k heap (``heapq.nlargest``, O(n log k))
          over a two-tier composite key: direct-vote tier (a directly-matched
          seed outranks every propagated-only neighbour), then the pre-fan-out
          direct-vote count within the seed tier (accumulated vote score for
          propagated-only neighbours), then pattern id ascending -- deterministic
          throughout.

        Bounded by two ceilings: ``_SEED_CAP`` before fan-out and ``_TOPK_CAP``
        after. Votes are transparent integer counts, never a tuned score.
        """
        k = min(max(int(k), 1), _TOPK_CAP)

        # 1. Direct hydration: matched signal -> seed pattern(s), one vote each.
        unmatched: list[str] = []
        direct_votes: dict[str, int] = {}
        for sid in matched_signal_ids or []:
            entry = self._signal_index.get(sid)
            if entry is None:
                unmatched.append(sid)
                continue
            for pid in entry["pattern_ids"]:
                direct_votes[pid] = direct_votes.get(pid, 0) + 1

        # Empty leg: recognised signals that hydrate to nothing -> abstain.
        if not direct_votes:
            return RetrievalResult(
                state=NO_MATCH,
                unmatched_signals=sorted(set(unmatched)),
                reason="no matched signal maps to a corpus pattern",
            )

        # 2. Seed cap BEFORE fan-out: rank seeds (weight desc, id asc), bound.
        seeds = sorted(direct_votes.items(), key=lambda kv: (-kv[1], kv[0]))[:_SEED_CAP]

        # 3. Vote tally seeded from the capped seeds' direct votes.
        scores: dict[str, int] = dict(seeds)
        dangling: set[str] = set()

        # 4. One-hop fan-out: propagate each seed's weight to its ``alternatives``.
        if fan_out:
            for pid, weight in seeds:
                seed_pat = self._lookup_pattern(pid)
                if seed_pat is None:
                    continue
                for neighbour in seed_pat.get("alternatives", []):
                    if self._lookup_pattern(neighbour) is None:
                        dangling.add(neighbour)   # typed dangling, surfaced loud
                        continue
                    scores[neighbour] = scores.get(neighbour, 0) + weight

        # 5. Top-k via heap-top-k over a TWO-TIER composite key. Pre-order
        #    candidates by id asc so nlargest's stable decoration breaks full
        #    ties by pattern_id ascending -- the tertiary key. The key is
        #    (direct-vote tier, then the pre-fan-out direct-vote COUNT within the
        #    seed tier, else the accumulated vote score): a directly-matched seed
        #    (tier True) outranks every propagated-only neighbour (tier False)
        #    regardless of score, so no zero-direct-vote hub can evict a gold
        #    seed under the k cap; and seeds rank by direct-vote count, not
        #    accumulated score, so fan-out cannot re-order the seed tier.
        ordered = sorted(scores.items())
        top = heapq.nlargest(
            k,
            ordered,
            key=lambda kv: (
                kv[0] in direct_votes,
                direct_votes[kv[0]] if kv[0] in direct_votes else kv[1],
            ),
        )

        # 6. Hydrate the winners into the envelope; never emit a husk. Each pattern
        #    is deep-frozen at this boundary: a shallow ``{**pat}`` would alias the
        #    singleton corpus's nested lists, so a caller mutating a returned
        #    pattern would corrupt the shared corpus. deep_freeze severs every
        #    reference and seals the copy, JSON-serialisable throughout.
        patterns: list[dict] = []
        votes: dict[str, int] = {}
        for pid, score in top:
            pat = self._lookup_pattern(pid)
            if pat is None:
                dangling.add(pid)
                continue
            direct = direct_votes.get(pid, 0)
            patterns.append(deep_freeze({
                **pat,
                "retrieval": {
                    "score": score,
                    "direct_votes": direct,
                    "propagated_votes": score - direct,
                    "seed": pid in direct_votes,
                },
            }))
            votes[pid] = score

        # 7. Resolve the envelope state (fail closed).
        if not patterns:
            return RetrievalResult(
                state=DANGLING,
                dangling=sorted(dangling),
                unmatched_signals=sorted(set(unmatched)),
                reason="hydrated pattern ids did not resolve to corpus patterns",
            )
        top_score = patterns[0]["retrieval"]["score"]
        if top_score >= _CONFIDENCE_FLOOR:
            state, reason = HIT, ""
        else:
            state = LOW_CONFIDENCE
            reason = f"best score {top_score} below confidence floor {_CONFIDENCE_FLOOR}"
        return RetrievalResult(
            state=state,
            patterns=patterns,
            votes=votes,
            dangling=sorted(dangling),
            unmatched_signals=sorted(set(unmatched)),
            reason=reason,
        )


class KnowledgeLoader(_SignalEngine):
    """Loads and queries the Mnemos knowledge base (structures, complexities,
    decision rules).

    All matching is structural / exact / data-driven.  No fuzzy keyword overlap.
    Inherits the Shape-C signal-index retrieval engine (:class:`_SignalEngine`).
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, knowledge_dir: Path | None = None) -> None:
        self._dir = knowledge_dir or _KNOWLEDGE_DIR

        with open(self._dir / "structures.json", encoding="utf-8") as f:
            self._structures_data = json.load(f)

        with open(self._dir / "complexities.json", encoding="utf-8") as f:
            self._complexities_data = json.load(f)

        # Build convenience indices.
        self._structures: list[dict] = self._structures_data["structures"]
        self._ds_operations: dict = self._complexities_data["data_structure_operations"]
        self._sorting: dict = self._complexities_data["sorting_algorithms"]
        self._input_guidelines: dict = self._complexities_data["input_size_guidelines"]
        self._constraint_guide: list[dict] = self._complexities_data["constraint_to_complexity_guide"]

        # Index: pattern_id -> (structure_id, pattern_dict)
        self._pattern_index: dict[str, tuple[str, dict]] = {}
        for struct in self._structures:
            for pat in struct.get("patterns", []):
                self._pattern_index[pat["id"]] = (struct["id"], pat)

        # Index: structure_id -> structure_dict
        self._structure_index: dict[str, dict] = {s["id"]: s for s in self._structures}

        # Build max-n map from input_size_guidelines.
        self._max_n_for_complexity: dict[str, int | float] = {}
        for comp, info in self._input_guidelines.items():
            max_n = info.get("max_n")
            if max_n == "any":
                self._max_n_for_complexity[comp] = float("inf")
            elif isinstance(max_n, (int, float)):
                self._max_n_for_complexity[comp] = max_n

        # Shape-C signal index (from patterns' structural_signals). Built at load
        # so a hash collision fails CLOSED here, not at first query.
        self._build_signal_index()

    # ------------------------------------------------------------------
    # Pure retrieval
    # ------------------------------------------------------------------

    def get_structure(self, structure_id: str) -> dict | None:
        """Get full structure entry by ID."""
        return self._structure_index.get(structure_id)

    def get_pattern(self, pattern_id: str) -> dict | None:
        """Get a specific pattern by ID (searches across all structures)."""
        entry = self._pattern_index.get(pattern_id)
        if entry is None:
            return None
        structure_id, pat = entry
        result = dict(pat)
        result["structure_id"] = structure_id
        return result

    def get_structures_by_ids(self, ids: list[str]) -> list[dict]:
        """Batch retrieval of structures by ID."""
        results: list[dict] = []
        for sid in ids:
            s = self._structure_index.get(sid)
            if s is not None:
                results.append(s)
        return results

    def get_all_structures(self) -> list[dict]:
        """Get all structure entries."""
        return list(self._structures)

    def get_all_patterns(self) -> list[dict]:
        """Get all patterns across all structures.  Each includes
        ``structure_id``."""
        patterns: list[dict] = []
        for struct in self._structures:
            for pat in struct.get("patterns", []):
                entry = dict(pat)
                entry["structure_id"] = struct["id"]
                patterns.append(entry)
        return patterns

    def get_alternatives(self, pattern_id: str) -> list[dict]:
        """Find alternatives for *pattern_id* with ``when_better`` reasoning.

        Returns a list of ``{id, name, when_better, complexity}`` dicts.
        """
        entry = self._pattern_index.get(pattern_id)
        if entry is None:
            return []

        _, pat = entry
        alt_ids: list[str] = pat.get("alternatives", [])
        results: list[dict] = []

        for alt_id in alt_ids:
            alt_entry = self._pattern_index.get(alt_id)
            if alt_entry is None:
                results.append({"id": alt_id, "name": alt_id, "when_better": None, "complexity": None})
                continue

            _, alt_pat = alt_entry

            when_better_hints: list[str] = []
            original_avoid = pat.get("avoid_when", [])
            if original_avoid:
                when_better_hints.extend(original_avoid)
            else:
                when_better_hints.extend(alt_pat.get("applies_when", [])[:2])

            results.append(
                {
                    "id": alt_pat["id"],
                    "name": alt_pat.get("name", alt_pat["id"]),
                    "when_better": when_better_hints or None,
                    "complexity": alt_pat.get("complexity"),
                }
            )

        return results

    def get_complexity(self, data_structure: str, operation: str) -> dict | None:
        """Direct lookup of a data-structure operation complexity."""
        ds = self._ds_operations.get(data_structure)
        if ds is None:
            return None
        comp = ds.get(operation)
        if comp is None:
            return None
        return {
            "data_structure": data_structure,
            "operation": operation,
            "complexity": comp,
        }

    def get_sorting_complexities(self) -> list[dict]:
        """Get sorting algorithm complexities as a list of dicts."""
        results: list[dict] = []
        for algo_id, info in self._sorting.items():
            entry = dict(info)
            entry["id"] = algo_id
            results.append(entry)
        return results

    def get_input_size_guide(self) -> list[dict]:
        """Get practical input-size guidelines as a list of dicts."""
        results: list[dict] = []
        for comp, info in self._input_guidelines.items():
            entry = dict(info)
            entry["complexity"] = comp
            results.append(entry)
        return results

    def get_compact_index(self) -> list[dict]:
        """Return id + name + structural_signals only, for each pattern.

        Useful for the agent to scan available patterns without pulling
        full details.
        """
        results: list[dict] = []
        for struct in self._structures:
            for pat in struct.get("patterns", []):
                results.append({
                    "id": pat["id"],
                    "name": pat.get("name", pat["id"]),
                    "structure": struct["id"],
                    "structural_signals": pat.get("structural_signals", []),
                })
        return results

    # ------------------------------------------------------------------
    # Constraint filtering — data-driven from complexities.json
    # ------------------------------------------------------------------

    def filter_by_constraints(
        self,
        patterns: list[dict],
        constraints: dict,
    ) -> tuple[list[dict], list[dict]]:
        """Filter patterns by constraints using input_size_guidelines from JSON.

        Args:
            patterns: List of pattern dicts (each must have ``complexity``
                with ``time`` and/or ``space`` keys).
            constraints: Dict with optional keys:
                - ``n`` or ``input_size`` (int): max input size
                - ``space`` (str): max space complexity, e.g. "O(1)"
                - ``target_complexity`` (str): max time complexity desired

        Returns:
            (surviving, filtered_out) where each filtered_out entry has
            a ``filter_reason`` key explaining why it was removed.
        """
        n = constraints.get("n") or constraints.get("input_size")
        max_space = constraints.get("space")
        target_complexity = constraints.get("target_complexity")

        surviving: list[dict] = []
        filtered_out: list[dict] = []

        for pat in patterns:
            complexity = pat.get("complexity", {})
            if isinstance(complexity, str):
                complexity = {}
            time_str = complexity.get("time", "") if isinstance(complexity, dict) else ""
            space_str = complexity.get("space", "") if isinstance(complexity, dict) else ""

            reason = None

            # --- input_size filter (data-driven from JSON) ---
            if n is not None and isinstance(n, (int, float)) and time_str:
                n = int(n)
                time_rank_val = _rank(time_str)
                tier_key = _COMPLEXITY_RANK[time_rank_val] if time_rank_val < len(_COMPLEXITY_RANK) else None
                max_n = self._max_n_for_complexity.get(tier_key, 0) if tier_key else 0
                if n > max_n:
                    reason = f"{time_str} infeasible for n={n:,}"

            # --- space filter ---
            if reason is None and max_space and space_str:
                if _rank(space_str) > _rank(max_space):
                    reason = f"space {space_str} exceeds max {max_space}"

            # --- target complexity filter ---
            if reason is None and target_complexity and time_str:
                if _rank(time_str) > _rank(target_complexity):
                    reason = f"{time_str} exceeds target {target_complexity}"

            if reason:
                entry = dict(pat)
                entry["filter_reason"] = reason
                filtered_out.append(entry)
            else:
                surviving.append(pat)

        return surviving, filtered_out

    # ------------------------------------------------------------------
    # Complexity ranking helper (public, for use by _shared.py)
    # ------------------------------------------------------------------

    def max_feasible_complexity_rank(self, n: int) -> int:
        """Given input size *n*, return the max complexity rank that is
        feasible, using input_size_guidelines from the JSON.

        Returns the rank index into _COMPLEXITY_RANK.
        """
        best_rank = 0  # default to O(1) only
        for comp_str, max_n in self._max_n_for_complexity.items():
            if n <= max_n:
                rank = _rank(comp_str)
                best_rank = max(best_rank, rank)
        return best_rank
