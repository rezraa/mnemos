# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""JSON file-backed CRUD store for Mnemos memory with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .schemas import (
    CodebaseContext,
    Correction,
    Decision,
    DecisionOutcome,
    Regression,
)


def _default_memory_dir() -> Path:
    """Return the default memory directory, respecting MNEMOS_MEMORY_DIR."""
    env = os.environ.get("MNEMOS_MEMORY_DIR")
    if env:
        return Path(env)
    return Path.home() / ".mnemos" / "memory"


class MemoryStore:
    """Persistent JSON file store for decisions, regressions, corrections, and
    codebase contexts.

    Each collection is stored in its own JSON file.  Writes are atomic
    (write-to-temp then ``os.rename``) so a crash mid-write never corrupts
    the store.
    """

    DECISIONS_FILE = "decisions.json"
    REGRESSIONS_FILE = "regressions.json"
    CORRECTIONS_FILE = "corrections.json"
    CONTEXTS_FILE = "contexts.json"

    def __init__(self, memory_dir: Path | None = None) -> None:
        self._dir = Path(memory_dir) if memory_dir else _default_memory_dir()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, filename: str) -> Path:
        return self._dir / filename

    def _load(self, filename: str) -> list[dict[str, Any]]:
        """Load a JSON list from *filename*, returning [] if missing or empty."""
        path = self._filepath(filename)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, filename: str, data: list[dict[str, Any]]) -> None:
        """Atomically write *data* as JSON to *filename*.

        Strategy: write to a temp file in the same directory, then
        ``os.rename`` (atomic on POSIX when src/dst are on the same FS).
        """
        self._ensure_dir()
        target = self._filepath(filename)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._dir, prefix=f".{filename}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.rename(tmp_path, target)
        except BaseException:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _append(self, filename: str, record: dict[str, Any]) -> None:
        """Load, append, save."""
        records = self._load(filename)
        records.append(record)
        self._save(filename, records)

    # ------------------------------------------------------------------
    # Decision operations
    # ------------------------------------------------------------------

    def log_decision(self, decision: Decision) -> str:
        """Persist a decision and return its id."""
        self._append(self.DECISIONS_FILE, decision.model_dump(mode="json"))
        return decision.id

    def get_decisions(
        self,
        project_id: str | None = None,
        pattern: str | None = None,
        outcome: DecisionOutcome | None = None,
    ) -> list[Decision]:
        """Return decisions, optionally filtered."""
        raw = self._load(self.DECISIONS_FILE)
        results: list[Decision] = []
        for entry in raw:
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
        """Persist a regression and return its id."""
        self._append(self.REGRESSIONS_FILE, regression.model_dump(mode="json"))
        return regression.id

    def get_regressions(
        self,
        pattern: str | None = None,
        project_id: str | None = None,
    ) -> list[Regression]:
        raw = self._load(self.REGRESSIONS_FILE)
        results: list[Regression] = []
        for entry in raw:
            if pattern and entry.get("pattern") != pattern:
                continue
            if project_id and entry.get("project_id") != project_id:
                continue
            results.append(Regression.model_validate(entry))
        return results

    def check_regression(self, pattern: str, ds: str) -> Regression | None:
        """Return the most recent regression matching *pattern* + *ds*, or None."""
        raw = self._load(self.REGRESSIONS_FILE)
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
        """Persist a correction and return its id."""
        self._append(self.CORRECTIONS_FILE, correction.model_dump(mode="json"))
        return correction.id

    def get_corrections(
        self,
        project_id: str | None = None,
    ) -> list[Correction]:
        raw = self._load(self.CORRECTIONS_FILE)
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
        """Upsert a codebase context (keyed on project_id). Returns project_id."""
        raw = self._load(self.CONTEXTS_FILE)
        new_entry = context.model_dump(mode="json")
        # Replace existing entry for this project_id, or append
        replaced = False
        for i, entry in enumerate(raw):
            if entry.get("project_id") == context.project_id:
                raw[i] = new_entry
                replaced = True
                break
        if not replaced:
            raw.append(new_entry)
        self._save(self.CONTEXTS_FILE, raw)
        return context.project_id

    def get_context(self, project_id: str) -> CodebaseContext | None:
        raw = self._load(self.CONTEXTS_FILE)
        for entry in raw:
            if entry.get("project_id") == project_id:
                return CodebaseContext.model_validate(entry)
        return None

    # ------------------------------------------------------------------
    # Stats / analytics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return high-level memory statistics."""
        decisions = self._load(self.DECISIONS_FILE)
        regressions = self._load(self.REGRESSIONS_FILE)
        corrections = self._load(self.CORRECTIONS_FILE)

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
        decisions = self._load(self.DECISIONS_FILE)

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
