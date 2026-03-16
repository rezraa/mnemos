# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""Knowledge loader for Mnemos-MCP.

Loads structures.json, complexities.json, and decision_rules.json and provides
pure retrieval, structural signal matching (exact against decision_rules),
and constraint filtering (data-driven from complexities.json).

No fuzzy keyword matching.  No tokenization.  No Jaccard scoring.
"""

from __future__ import annotations

import json
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


class KnowledgeLoader:
    """Loads and queries the Mnemos knowledge base (structures, complexities,
    decision rules).

    All matching is structural / exact / data-driven.  No fuzzy keyword overlap.
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

        with open(self._dir / "decision_rules.json", encoding="utf-8") as f:
            self._decision_rules_data = json.load(f)

        # Build convenience indices.
        self._structures: list[dict] = self._structures_data["structures"]
        self._rules: list[dict] = self._decision_rules_data["rules"]
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

        # Build rule index: normalised structural_signal -> rule
        # Used for exact substring matching in match_structural_signals().
        self._rule_signal_index: dict[str, dict] = {}
        for rule in self._rules:
            signal = rule.get("structural_signal", "").lower().strip()
            if signal:
                self._rule_signal_index[signal] = rule

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
    # Structural matching — exact against decision_rules.json
    # ------------------------------------------------------------------

    def match_structural_signals(self, signals: list[str]) -> list[dict]:
        """Given structural signals identified by the agent, find matching
        decision rules.

        Matching is exact substring on the ``structural_signal`` field of
        each rule — NOT fuzzy keyword overlap.

        Returns matching rules augmented with full pattern details::

            [{"rule": {...}, "recommended_pattern": {...},
              "alternatives": [...], "structure": "..."}]
        """
        if not signals:
            return []

        results: list[dict] = []
        seen_rule_ids: set[str] = set()

        for signal in signals:
            signal_lower = signal.lower().strip()
            if not signal_lower:
                continue

            for rule_signal, rule in self._rule_signal_index.items():
                if rule["id"] in seen_rule_ids:
                    continue

                # Exact substring match: the agent's signal appears in the
                # rule's structural_signal, or vice versa.
                if signal_lower in rule_signal or rule_signal in signal_lower:
                    seen_rule_ids.add(rule["id"])

                    # Resolve recommended pattern
                    rec_pattern_id = rule.get("recommended_pattern", "")
                    rec_pattern = self.get_pattern(rec_pattern_id)

                    # Resolve alternatives
                    alt_ids = rule.get("alternatives", [])
                    alternatives = []
                    for alt_id in alt_ids:
                        alt_pat = self.get_pattern(alt_id)
                        if alt_pat:
                            alternatives.append(alt_pat)
                        else:
                            alternatives.append({"id": alt_id, "name": alt_id})

                    results.append({
                        "rule": rule,
                        "signal": signal,
                        "recommended_pattern": rec_pattern,
                        "recommended_structure": rule.get("recommended_structure", ""),
                        "alternatives": alternatives,
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
