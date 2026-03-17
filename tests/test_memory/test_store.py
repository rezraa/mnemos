# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for MemoryStore."""

import json
import pytest
from pathlib import Path

from mnemos.memory.schemas import (
    CodebaseContext,
    Correction,
    Decision,
    DecisionMode,
    DecisionOutcome,
    Regression,
    Severity,
    StructureFound,
)
from mnemos.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    """Fresh MemoryStore backed by a temp directory."""
    return MemoryStore(memory_dir=tmp_path)


# ------------------------------------------------------------------
# Decision CRUD
# ------------------------------------------------------------------

def test_log_and_retrieve_decision(store: MemoryStore):
    decision = Decision(
        mode=DecisionMode.plan,
        problem_description="Two sum problem",
        pattern_chosen="hash-lookup",
        ds_chosen="hashmap",
        outcome=DecisionOutcome.accepted,
        project_id="proj-1",
    )
    did = store.log_decision(decision)
    assert did == decision.id

    decisions = store.get_decisions()
    assert len(decisions) == 1
    assert decisions[0].pattern_chosen == "hash-lookup"
    assert decisions[0].project_id == "proj-1"


def test_filter_decisions_by_project(store: MemoryStore):
    for pid in ("proj-a", "proj-b", "proj-a"):
        store.log_decision(Decision(
            mode=DecisionMode.plan,
            problem_description="test",
            pattern_chosen="x",
            ds_chosen="y",
            project_id=pid,
        ))

    assert len(store.get_decisions(project_id="proj-a")) == 2
    assert len(store.get_decisions(project_id="proj-b")) == 1
    assert len(store.get_decisions(project_id="proj-c")) == 0


def test_filter_decisions_by_outcome(store: MemoryStore):
    for outcome in (DecisionOutcome.accepted, DecisionOutcome.rejected, DecisionOutcome.accepted):
        store.log_decision(Decision(
            mode=DecisionMode.review,
            problem_description="test",
            pattern_chosen="x",
            ds_chosen="y",
            outcome=outcome,
            project_id="p",
        ))

    assert len(store.get_decisions(outcome=DecisionOutcome.accepted)) == 2
    assert len(store.get_decisions(outcome=DecisionOutcome.rejected)) == 1
    assert len(store.get_decisions(outcome=DecisionOutcome.regressed)) == 0


# ------------------------------------------------------------------
# Regression CRUD
# ------------------------------------------------------------------

def test_log_regression(store: MemoryStore):
    reg = Regression(
        pattern="nested-loop",
        ds="array",
        description="Timed out on n=100k",
        severity=Severity.high,
        project_id="proj-1",
    )
    rid = store.add_regression(reg)
    assert rid == reg.id

    regressions = store.get_regressions()
    assert len(regressions) == 1
    assert regressions[0].pattern == "nested-loop"
    assert regressions[0].severity == Severity.high


def test_check_regression(store: MemoryStore):
    store.add_regression(Regression(
        pattern="brute-force",
        ds="array",
        description="Too slow",
        project_id="p",
    ))
    store.add_regression(Regression(
        pattern="brute-force",
        ds="array",
        description="Still too slow",
        project_id="p",
    ))

    result = store.check_regression(pattern="brute-force", ds="array")
    assert result is not None
    # Should return the most recent one.
    assert result.description == "Still too slow"

    # No match for different pattern.
    assert store.check_regression(pattern="binary-search", ds="array") is None


# ------------------------------------------------------------------
# Correction CRUD
# ------------------------------------------------------------------

def test_log_correction(store: MemoryStore):
    corr = Correction(
        original_pattern="nested-loop",
        corrected_pattern="hash-lookup",
        reason="O(n^2) -> O(n)",
        project_id="proj-1",
    )
    cid = store.add_correction(corr)
    assert cid == corr.id

    corrections = store.get_corrections()
    assert len(corrections) == 1
    assert corrections[0].original_pattern == "nested-loop"
    assert corrections[0].corrected_pattern == "hash-lookup"


# ------------------------------------------------------------------
# Context CRUD
# ------------------------------------------------------------------

def test_set_and_get_context(store: MemoryStore):
    ctx = CodebaseContext(
        project_id="proj-ctx",
        project_path="/tmp/myproject",
        language="python",
        structures_found=[
            StructureFound(type="hashmap", location="main.py", usage="caching"),
        ],
        runtime_constraints="max memory 512MB",
    )
    pid = store.set_context(ctx)
    assert pid == "proj-ctx"

    retrieved = store.get_context("proj-ctx")
    assert retrieved is not None
    assert retrieved.language == "python"
    assert len(retrieved.structures_found) == 1
    assert retrieved.runtime_constraints == "max memory 512MB"

    # Non-existent project returns None.
    assert store.get_context("nonexistent") is None

    # Upsert: update the same project_id.
    ctx2 = CodebaseContext(
        project_id="proj-ctx",
        project_path="/tmp/myproject",
        language="go",
    )
    store.set_context(ctx2)
    updated = store.get_context("proj-ctx")
    assert updated is not None
    assert updated.language == "go"


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

def test_get_stats(store: MemoryStore):
    store.log_decision(Decision(
        mode=DecisionMode.plan, problem_description="a",
        pattern_chosen="x", ds_chosen="y",
        outcome=DecisionOutcome.accepted, project_id="p",
    ))
    store.log_decision(Decision(
        mode=DecisionMode.review, problem_description="b",
        pattern_chosen="z", ds_chosen="w",
        outcome=DecisionOutcome.rejected, project_id="p",
    ))
    store.add_regression(Regression(
        pattern="z", ds="w", description="bad", project_id="p",
    ))

    stats = store.get_stats()
    assert stats["total_decisions"] == 2
    assert stats["accepted"] == 1
    assert stats["rejected"] == 1
    assert stats["total_regressions"] == 1
    assert "accuracy_rate" in stats


def test_get_pattern_stats(store: MemoryStore):
    for _ in range(3):
        store.log_decision(Decision(
            mode=DecisionMode.plan, problem_description="a",
            pattern_chosen="sliding-window", ds_chosen="array",
            outcome=DecisionOutcome.accepted, project_id="p",
        ))
    store.log_decision(Decision(
        mode=DecisionMode.plan, problem_description="b",
        pattern_chosen="two-pointer", ds_chosen="array",
        outcome=DecisionOutcome.rejected, project_id="p",
    ))

    ps = store.get_pattern_stats()
    assert ps["pattern_usage"]["sliding-window"] == 3
    assert ps["pattern_usage"]["two-pointer"] == 1
    assert "array" in ps["ds_distribution"]
    assert ps["pattern_outcomes"]["sliding-window"]["accepted"] == 3


# ------------------------------------------------------------------
# Persistence & atomicity
# ------------------------------------------------------------------

def test_persistence_across_instances(tmp_path: Path):
    """Data written by one store instance is readable by a new instance."""
    store1 = MemoryStore(memory_dir=tmp_path)
    store1.log_decision(Decision(
        mode=DecisionMode.plan, problem_description="persist test",
        pattern_chosen="x", ds_chosen="y",
        outcome=DecisionOutcome.accepted, project_id="p",
    ))

    store2 = MemoryStore(memory_dir=tmp_path)
    decisions = store2.get_decisions()
    assert len(decisions) == 1
    assert decisions[0].problem_description == "persist test"


def test_atomic_write(tmp_path: Path):
    """After a successful save the JSON file is valid and contains all records."""
    store = MemoryStore(memory_dir=tmp_path)
    for i in range(5):
        store.log_decision(Decision(
            mode=DecisionMode.plan,
            problem_description=f"decision-{i}",
            pattern_chosen="pat",
            ds_chosen="ds",
            project_id="p",
        ))

    # Directly load the file and verify it is valid JSON with 5 entries.
    filepath = tmp_path / MemoryStore.DECISIONS_FILE
    assert filepath.exists()

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == 5
