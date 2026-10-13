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

from mnemos.knowledge.loader import _SignalEngine, _rank

_KNOWLEDGE_DIR = Path(__file__).parent
_PREFIX = "mnemos:"


class GraphKnowledgeLoader(_SignalEngine):
    """KnowledgeLoader backed by Kuzu/LadybugDB.

    Pulls all patterns and edges from the graph on init and builds
    the same in-memory indices as KnowledgeLoader. After init, no more DB
    calls for reads. Inherits the ONE Shape-C signal-index retrieval engine
    (:class:`_SignalEngine`) over the shared ``self._pattern_index`` -- the same
    engine the JSON loader uses, no duplicate engine code.
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

        self._load_patterns()
        self._load_alternatives()

        # Shape-C signal index (from patterns' structural_signals), same engine
        # as the JSON loader. Built at load so a hash collision fails CLOSED here.
        self._build_signal_index()

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
            constraints = self._parse_json(constraints_s, {})
            data = self._parse_json(data_s, {})

            pat = {
                "id": bare_id,
                "name": name,
                "complexity": complexity,
                "structural_signals": signals,
                # KEEP the graph's constraints column: the query already selects
                # p.constraints, but the built pattern used to drop it, so the
                # graph loader diverged from the JSON loader (whose patterns carry
                # constraints from structures.json). filter_by_constraints and the
                # Shape-C complexity gate read this field -- dropping it silently
                # degraded graph-mode retrieval. Drift repaired (story-79321e96).
                "constraints": constraints,
                "use_when": data.get("use_when", []),
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

    def max_feasible_complexity_rank(self, n: int) -> int:
        best_rank = 0
        for comp_str, max_n in self._max_n_for_complexity.items():
            if n <= max_n:
                rank = _rank(comp_str)
                best_rank = max(best_rank, rank)
        return best_rank
