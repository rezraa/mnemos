# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Graph-backed knowledge loader for Mnemos.

Same interface as KnowledgeLoader but reads from a LadybugDB/Kuzu graph
database (Othrys) instead of JSON files. Caches everything on init —
after the initial DB read, all lookups are in-memory dict access, identical
to the JSON loader's performance.

All data including complexities reference data is loaded from the graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mnemos.knowledge.loader import (
    _COMPLEXITY_RANK,
    _rank,
)

_KNOWLEDGE_DIR = Path(__file__).parent
_PREFIX = "mnemos:"


class GraphKnowledgeLoader:
    """KnowledgeLoader backed by Kuzu/LadybugDB.

    Pulls all patterns, rules, and edges from the graph on init and builds
    the same in-memory indices as KnowledgeLoader. After init, no more DB
    calls for reads.
    """

    def __init__(self, conn: Any, knowledge_dir: Path | None = None) -> None:
        self._conn = conn
        self._dir = knowledge_dir or _KNOWLEDGE_DIR

        # Load complexities reference data from the graph
        complexities_data = self._load_complexities()

        self._ds_operations: dict = complexities_data["data_structure_operations"]
        self._sorting: dict = complexities_data["sorting_algorithms"]
        self._input_guidelines: dict = complexities_data["input_size_guidelines"]
        self._constraint_guide: list[dict] = complexities_data["constraint_to_complexity_guide"]

        self._max_n_for_complexity: dict[str, int | float] = {}
        for comp, info in self._input_guidelines.items():
            max_n = info.get("max_n")
            if max_n == "any":
                self._max_n_for_complexity[comp] = float("inf")
            elif isinstance(max_n, (int, float)):
                self._max_n_for_complexity[comp] = max_n

        # Pull everything from the graph and build indices
        self._pattern_index: dict[str, tuple[str, dict]] = {}
        self._structure_index: dict[str, dict] = {}
        self._rule_signal_index: dict[str, dict] = {}
        self._rules: list[dict] = []

        self._load_patterns()
        self._load_rules()
        self._load_alternatives()

    # ------------------------------------------------------------------
    # Graph loading (runs once on init)
    # ------------------------------------------------------------------

    def _load_complexities(self) -> dict:
        """Load complexities reference data from the agent node.

        Falls back to complexities.json on disk if the agent node doesn't
        have reference_data (e.g. older DB).
        """
        result = self._conn.execute(
            "MATCH (a:agents {id: 'mnemos'}) RETURN a.reference_data"
        )
        if result.has_next():
            raw = result.get_next()[0]
            if raw:
                parsed = self._parse_json(raw, None)
                if parsed is not None:
                    return parsed

        # Fallback for DBs without reference_data on agent
        with open(self._dir / "complexities.json", encoding="utf-8") as f:
            return json.load(f)

    def _load_patterns(self) -> None:
        """Pull all mnemos patterns from graph, build pattern + structure indices."""
        result = self._conn.execute(
            "MATCH (p:patterns) WHERE p.domain = 'mnemos' "
            "RETURN p.id, p.name, p.category, p.complexity, p.signals, "
            "       p.constraints, p.data "
            "ORDER BY p.id"
        )

        # Group patterns by category (= structure_id) to rebuild structures
        by_structure: dict[str, list[dict]] = {}

        while result.has_next():
            row = result.get_next()
            graph_id, name, category, complexity_s, signals_s, constraints_s, data_s = row

            bare_id = self._strip(graph_id)
            complexity = self._parse_json(complexity_s, {})
            signals = self._parse_json(signals_s, [])
            data = self._parse_json(data_s, {})

            pat = {
                "id": bare_id,
                "name": name,
                "complexity": complexity,
                "structural_signals": signals,
                "applies_when": data.get("applies_when", []),
                "avoid_when": data.get("avoid_when", []),
                "alternatives": [],  # filled in by _load_alternatives
            }

            self._pattern_index[bare_id] = (category, pat)
            by_structure.setdefault(category, []).append(pat)

            # Capture structure metadata from first pattern's data
            if category not in self._structure_index:
                self._structure_index[category] = {
                    "id": category,
                    "name": data.get("structure_name", category),
                    "operations": data.get("structure_operations", {}),
                    "patterns": [],
                }

        # Attach patterns to structures
        for struct_id, patterns in by_structure.items():
            if struct_id in self._structure_index:
                self._structure_index[struct_id]["patterns"] = patterns

    def _load_rules(self) -> None:
        """Pull all mnemos rules from graph, build signal index."""
        result = self._conn.execute(
            "MATCH (r:rules) WHERE r.domain = 'mnemos' "
            "RETURN r.id, r.signal, r.recommended_pattern, r.priority, r.data "
            "ORDER BY r.id"
        )

        while result.has_next():
            row = result.get_next()
            graph_id, signal, rec_pattern, priority, data_s = row

            bare_id = self._strip(graph_id)
            data = self._parse_json(data_s, {})

            rule = {
                "id": bare_id,
                "structural_signal": signal,
                "recommended_pattern": self._strip(rec_pattern) if rec_pattern else "",
                "recommended_structure": data.get("recommended_structure", ""),
                "alternatives": data.get("alternatives", []),
                "code_indicators": data.get("code_indicators", []),
                "constraints": data.get("constraints", {}),
            }

            self._rules.append(rule)
            norm_signal = signal.lower().strip()
            if norm_signal:
                self._rule_signal_index[norm_signal] = rule

    def _load_alternatives(self) -> None:
        """Pull alternative edges and attach to patterns."""
        result = self._conn.execute(
            "MATCH (a:patterns)-[:alternative]->(b:patterns) "
            "WHERE a.domain = 'mnemos' "
            "RETURN a.id, b.id"
        )

        while result.has_next():
            row = result.get_next()
            src_bare = self._strip(row[0])
            dst_bare = self._strip(row[1])

            entry = self._pattern_index.get(src_bare)
            if entry:
                _, pat = entry
                if dst_bare not in pat["alternatives"]:
                    pat["alternatives"].append(dst_bare)

    # ------------------------------------------------------------------
    # ID helpers
    # ------------------------------------------------------------------

    def _strip(self, graph_id: str) -> str:
        if graph_id and graph_id.startswith(_PREFIX):
            return graph_id[len(_PREFIX):]
        return graph_id or ""

    @staticmethod
    def _parse_json(raw: Any, default: Any = None) -> Any:
        """Decode a Kuzu value back to Python. Two accepted shapes:
        tagged-``JSON:`` strings and native list/dict. All other string
        forms are rejected per v3 invariant."""
        if raw is None:
            return default
        if isinstance(raw, (list, dict)):
            return raw
        if not isinstance(raw, str) or not raw:
            return default
        if not raw.startswith("JSON:"):
            return default
        body = raw[5:]
        if not body:
            return default
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return default

    # ------------------------------------------------------------------
    # Public API — same as KnowledgeLoader
    # ------------------------------------------------------------------

    def get_structure(self, structure_id: str) -> dict | None:
        return self._structure_index.get(structure_id)

    def get_pattern(self, pattern_id: str) -> dict | None:
        entry = self._pattern_index.get(pattern_id)
        if entry is None:
            return None
        structure_id, pat = entry
        result = dict(pat)
        result["structure_id"] = structure_id
        return result

    def get_structures_by_ids(self, ids: list[str]) -> list[dict]:
        results: list[dict] = []
        for sid in ids:
            s = self._structure_index.get(sid)
            if s is not None:
                results.append(s)
        return results

    def get_all_structures(self) -> list[dict]:
        return list(self._structure_index.values())

    def get_all_patterns(self) -> list[dict]:
        patterns: list[dict] = []
        for bare_id, (structure_id, pat) in self._pattern_index.items():
            entry = dict(pat)
            entry["structure_id"] = structure_id
            patterns.append(entry)
        return patterns

    def get_alternatives(self, pattern_id: str) -> list[dict]:
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

            results.append({
                "id": alt_pat["id"],
                "name": alt_pat.get("name", alt_pat["id"]),
                "when_better": when_better_hints or None,
                "complexity": alt_pat.get("complexity"),
            })

        return results

    def get_complexity(self, data_structure: str, operation: str) -> dict | None:
        ds = self._ds_operations.get(data_structure)
        if ds is None:
            return None
        comp = ds.get(operation)
        if comp is None:
            return None
        return {"data_structure": data_structure, "operation": operation, "complexity": comp}

    def get_sorting_complexities(self) -> list[dict]:
        results: list[dict] = []
        for algo_id, info in self._sorting.items():
            entry = dict(info)
            entry["id"] = algo_id
            results.append(entry)
        return results

    def get_input_size_guide(self) -> list[dict]:
        results: list[dict] = []
        for comp, info in self._input_guidelines.items():
            entry = dict(info)
            entry["complexity"] = comp
            results.append(entry)
        return results

    def get_compact_index(self) -> list[dict]:
        results: list[dict] = []
        for bare_id, (structure_id, pat) in self._pattern_index.items():
            results.append({
                "id": bare_id,
                "name": pat.get("name", bare_id),
                "structure": structure_id,
                "structural_signals": pat.get("structural_signals", []),
            })
        return results

    # ------------------------------------------------------------------
    # Structural matching — same logic as KnowledgeLoader
    # ------------------------------------------------------------------

    def match_structural_signals(self, signals: list[str]) -> list[dict]:
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

                if signal_lower in rule_signal or rule_signal in signal_lower:
                    seen_rule_ids.add(rule["id"])

                    rec_pattern_id = rule.get("recommended_pattern", "")
                    rec_pattern = self.get_pattern(rec_pattern_id)

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
    # Constraint filtering — pure logic, same as KnowledgeLoader
    # ------------------------------------------------------------------

    def filter_by_constraints(
        self,
        patterns: list[dict],
        constraints: dict,
    ) -> tuple[list[dict], list[dict]]:
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

            if n is not None and isinstance(n, (int, float)) and time_str:
                n = int(n)
                time_rank_val = _rank(time_str)
                tier_key = _COMPLEXITY_RANK[time_rank_val] if time_rank_val < len(_COMPLEXITY_RANK) else None
                max_n = self._max_n_for_complexity.get(tier_key, 0) if tier_key else 0
                if n > max_n:
                    reason = f"{time_str} infeasible for n={n:,}"

            if reason is None and max_space and space_str:
                if _rank(space_str) > _rank(max_space):
                    reason = f"space {space_str} exceeds max {max_space}"

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

    def max_feasible_complexity_rank(self, n: int) -> int:
        best_rank = 0
        for comp_str, max_n in self._max_n_for_complexity.items():
            if n <= max_n:
                rank = _rank(comp_str)
                best_rank = max(best_rank, rank)
        return best_rank
