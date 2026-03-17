# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Kuzu/LadybugDB-backed memory store for Mnemos graph mode.

Same public API as MemoryStore but reads/writes to the Kuzu `memories`
table instead of JSON files. Each memory record is stored as a node with
the decision/regression/correction data serialised in the `content` JSON
blob. The `agent` field is always "mnemos" and the `type` field maps to
the memory kind ("decision", "regression", "correction", "context").

Used when Mnemos is summoned inside Othrys (conn is provided).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .schemas import (
    CodebaseContext,
    Correction,
    Decision,
    DecisionOutcome,
    Regression,
    _short_id,
)

AGENT = "mnemos"


class GraphMemoryStore:
    """Kuzu-backed memory store — drop-in replacement for MemoryStore.

    All memory types are stored in the shared `memories` node table with:
        id, agent, project, timestamp, type, content (JSON blob)

    The content blob holds the full Pydantic model data so nothing is lost.
    Relationship edges (decided_by, related_to) are wired for Phoebe to
    query across agents and patterns.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _insert_memory(
        self,
        memory_id: str,
        project: str,
        memory_type: str,
        content: dict[str, Any],
    ) -> None:
        """Insert a memory node into Kuzu."""
        self._conn.execute(
            "CREATE (m:memories {"
            "  id: $id, agent: $agent, project: $project,"
            "  timestamp: $ts, type: $type, content: $content"
            "})",
            {
                "id": memory_id,
                "agent": AGENT,
                "project": project,
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": memory_type,
                "content": json.dumps(content, default=str),
            },
        )

    def _wire_decided_by(self, memory_id: str) -> None:
        """Create decided_by edge from memory to agent."""
        try:
            self._conn.execute(
                "MATCH (m:memories {id: $mid}), (a:agents {id: $aid}) "
                "CREATE (m)-[:decided_by]->(a)",
                {"mid": memory_id, "aid": AGENT},
            )
        except Exception:
            pass  # agent node may not exist in test DBs

    def _wire_related_to(self, memory_id: str, pattern_id: str) -> None:
        """Create related_to edge from memory to pattern."""
        # Pattern IDs in Kuzu are prefixed with "mnemos:"
        full_id = f"mnemos:{pattern_id}" if ":" not in pattern_id else pattern_id
        try:
            self._conn.execute(
                "MATCH (m:memories {id: $mid}), (p:patterns {id: $pid}) "
                "CREATE (m)-[:related_to]->(p)",
                {"mid": memory_id, "pid": full_id},
            )
        except Exception:
            pass  # pattern may not exist

    def _query_memories(
        self, memory_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Query memories by type with optional filters on content fields."""
        result = self._conn.execute(
            "MATCH (m:memories) WHERE m.agent = $agent AND m.type = $type "
            "RETURN m.id, m.project, m.timestamp, m.content "
            "ORDER BY m.timestamp DESC",
            {"agent": AGENT, "type": memory_type},
        )
        rows = []
        while result.has_next():
            row = result.get_next()
            content = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            # Apply filters on content fields
            if filters:
                skip = False
                for key, val in filters.items():
                    if val is not None and content.get(key) != val:
                        skip = True
                        break
                if skip:
                    continue
            rows.append(content)
        return rows

    # ------------------------------------------------------------------
    # Decision operations
    # ------------------------------------------------------------------

    def log_decision(self, decision: Decision) -> str:
        """Persist a decision to Kuzu and return its id."""
        data = decision.model_dump(mode="json")
        memory_id = f"d-{decision.id}"

        self._insert_memory(
            memory_id=memory_id,
            project=decision.project_id,
            memory_type="decision",
            content=data,
        )

        # Wire graph edges
        self._wire_decided_by(memory_id)
        if decision.pattern_chosen:
            self._wire_related_to(memory_id, decision.pattern_chosen)

        return decision.id

    def get_decisions(
        self,
        project_id: str | None = None,
        pattern: str | None = None,
        outcome: DecisionOutcome | None = None,
    ) -> list[Decision]:
        """Return decisions, optionally filtered."""
        rows = self._query_memories("decision")
        results: list[Decision] = []
        for entry in rows:
            if project_id and entry.get("project_id") != project_id:
                continue
            if pattern and entry.get("pattern_chosen") != pattern:
                continue
            if outcome and entry.get("outcome") != outcome.value:
                continue
            results.append(Decision.model_validate(entry))
        return results

    # ------------------------------------------------------------------
    # Regression operations
    # ------------------------------------------------------------------

    def add_regression(self, regression: Regression) -> str:
        """Persist a regression to Kuzu and return its id."""
        data = regression.model_dump(mode="json")
        memory_id = f"r-{regression.id}"

        self._insert_memory(
            memory_id=memory_id,
            project=regression.project_id,
            memory_type="regression",
            content=data,
        )

        self._wire_decided_by(memory_id)
        if regression.pattern:
            self._wire_related_to(memory_id, regression.pattern)

        return regression.id

    def get_regressions(
        self,
        pattern: str | None = None,
        project_id: str | None = None,
    ) -> list[Regression]:
        raw = self._query_memories("regression")
        results: list[Regression] = []
        for entry in raw:
            if pattern and entry.get("pattern") != pattern:
                continue
            if project_id and entry.get("project_id") != project_id:
                continue
            results.append(Regression.model_validate(entry))
        return results

    def check_regression(self, pattern: str, ds: str) -> Regression | None:
        """Return the most recent regression matching pattern + ds, or None."""
        raw = self._query_memories("regression")
        match: Regression | None = None
        for entry in raw:
            if entry.get("pattern") == pattern and entry.get("ds") == ds:
                candidate = Regression.model_validate(entry)
                if match is None or candidate.timestamp > match.timestamp:
                    match = candidate
        return match

    # ------------------------------------------------------------------
    # Correction operations
    # ------------------------------------------------------------------

    def add_correction(self, correction: Correction) -> str:
        """Persist a correction to Kuzu and return its id."""
        data = correction.model_dump(mode="json")
        memory_id = f"c-{correction.id}"

        self._insert_memory(
            memory_id=memory_id,
            project=correction.project_id,
            memory_type="correction",
            content=data,
        )

        self._wire_decided_by(memory_id)
        if correction.corrected_pattern:
            self._wire_related_to(memory_id, correction.corrected_pattern)

        return correction.id

    def get_corrections(
        self,
        project_id: str | None = None,
    ) -> list[Correction]:
        raw = self._query_memories("correction")
        results: list[Correction] = []
        for entry in raw:
            if project_id and entry.get("project_id") != project_id:
                continue
            results.append(Correction.model_validate(entry))
        return results

    # ------------------------------------------------------------------
    # Codebase context operations
    # ------------------------------------------------------------------

    def set_context(self, context: CodebaseContext) -> str:
        """Upsert a codebase context (keyed on project_id)."""
        data = context.model_dump(mode="json")
        memory_id = f"ctx-{context.project_id}"

        # Delete existing context for this project if any
        try:
            self._conn.execute(
                "MATCH (m:memories {id: $id}) DELETE m",
                {"id": memory_id},
            )
        except Exception:
            pass

        self._insert_memory(
            memory_id=memory_id,
            project=context.project_id,
            memory_type="context",
            content=data,
        )

        return context.project_id

    def get_context(self, project_id: str) -> CodebaseContext | None:
        raw = self._query_memories("context")
        for entry in raw:
            if entry.get("project_id") == project_id:
                return CodebaseContext.model_validate(entry)
        return None

    # ------------------------------------------------------------------
    # Stats (reads from graph)
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return high-level memory statistics."""
        decisions = self._query_memories("decision")
        regressions = self._query_memories("regression")
        corrections = self._query_memories("correction")

        total = len(decisions)
        accepted = sum(1 for d in decisions if d.get("outcome") == DecisionOutcome.accepted.value)
        rejected = sum(1 for d in decisions if d.get("outcome") == DecisionOutcome.rejected.value)
        regressed = sum(1 for d in decisions if d.get("outcome") == DecisionOutcome.regressed.value)
        accuracy_rate = (accepted / total * 100) if total else 0.0

        return {
            "total_decisions": total,
            "accepted": accepted,
            "rejected": rejected,
            "regressed": regressed,
            "accuracy_rate": round(accuracy_rate, 2),
            "total_regressions": len(regressions),
            "total_corrections": len(corrections),
            "regressions_avoided": max(0, len(corrections) - len(regressions)),
        }

    def get_pattern_stats(self) -> dict[str, Any]:
        """Return pattern usage frequency and DS distribution."""
        from collections import Counter

        decisions = self._query_memories("decision")

        pattern_counts: Counter[str] = Counter()
        ds_counts: Counter[str] = Counter()
        pattern_outcomes: dict[str, Counter[str]] = {}

        for d in decisions:
            pat = d.get("pattern_chosen", "unknown")
            ds = d.get("ds_chosen", "unknown")
            outcome = d.get("outcome", "unknown")

            pattern_counts[pat] += 1
            ds_counts[ds] += 1

            if pat not in pattern_outcomes:
                pattern_outcomes[pat] = Counter()
            pattern_outcomes[pat][outcome] += 1

        return {
            "pattern_usage": dict(pattern_counts.most_common()),
            "ds_distribution": dict(ds_counts.most_common()),
            "pattern_outcomes": {
                pat: dict(counts) for pat, counts in pattern_outcomes.items()
            },
        }
