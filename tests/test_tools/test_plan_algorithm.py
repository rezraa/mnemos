# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""Tests for the plan_algorithm tool."""

import pytest
from pathlib import Path
from unittest.mock import patch

from mnemos.memory.store import MemoryStore
from mnemos.memory.schemas import (
    Regression,
    Severity,
    CodebaseContext,
    StructureFound,
    PatternFound,
)
from mnemos.tools.plan_algorithm import plan_algorithm


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    """Monkey-patch the shared memory singleton to use a temp directory."""
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store), \
         patch("mnemos.tools.plan_algorithm.memory", temp_store):
        yield temp_store


# ------------------------------------------------------------------
# Structural signal matching
# ------------------------------------------------------------------

def test_structural_signal_returns_matched_rules():
    """Providing structural signals should match decision rules."""
    result = plan_algorithm(
        problem="find two numbers that sum to target",
        structural_signals=["unsorted input with pair"],
    )
    assert "matched_rules" in result
    assert len(result["matched_rules"]) > 0, "Expected at least one matched rule"

    first_rule = result["matched_rules"][0]
    assert "signal" in first_rule
    assert "recommended" in first_rule


def test_structural_signal_populates_consider():
    """Matched rules should produce entries in the consider list."""
    result = plan_algorithm(
        problem="find two numbers that sum to target",
        structural_signals=["unsorted input with pair"],
    )
    assert len(result["consider"]) > 0, "Expected at least one consider entry"

    first = result["consider"][0]
    assert "pattern_id" in first
    assert "name" in first
    assert "complexity" in first


def test_structures_param_returns_knowledge_slice():
    """Providing structure IDs should return knowledge slices."""
    result = plan_algorithm(
        problem="need a hashmap-based approach",
        structures=["hashmap"],
    )
    assert "hashmap" in result["knowledge"]
    km = result["knowledge"]["hashmap"]
    assert "patterns" in km
    assert len(km["patterns"]) > 0


# ------------------------------------------------------------------
# Constraint filtering
# ------------------------------------------------------------------

def test_constraint_filtering():
    """With n=10^6, O(n^2) patterns should be filtered out or demoted."""
    result = plan_algorithm(
        problem="find pairs in array",
        structural_signals=["sorted input with pair"],
        constraints={"n": 1_000_000},
    )

    for entry in result.get("consider", []):
        time_c = entry.get("complexity", {}).get("time", "")
        if "n^2" in time_c or "n^3" in time_c or "2^n" in time_c:
            assert entry.get("demoted", False), (
                f"Pattern {entry['pattern_id']} with {time_c} should be demoted for n=10^6"
            )


# ------------------------------------------------------------------
# Memory regression
# ------------------------------------------------------------------

def test_memory_regression_warning(_patch_memory):
    """If a regression exists for a matched pattern+ds, it should appear."""
    store: MemoryStore = _patch_memory

    # First, run to see what patterns are recommended.
    result = plan_algorithm(
        problem="find pair sum",
        structural_signals=["unsorted input with pair"],
    )
    if not result["consider"]:
        pytest.skip("No consider results to test regression against")

    first = result["consider"][0]
    pid = first["pattern_id"]
    ds = first.get("ds", first.get("structure_id", ""))

    if not pid or not ds:
        pytest.skip("Pattern has no ds to test regression against")

    store.add_regression(Regression(
        pattern=pid,
        ds=ds,
        description="Caused OOM on large input",
        severity=Severity.high,
        project_id="default",
    ))

    # Re-run — should now contain a regression warning.
    result2 = plan_algorithm(
        problem="find pair sum",
        structural_signals=["unsorted input with pair"],
    )

    has_regression_info = bool(result2.get("memory", {}).get("regressions"))
    has_warning = any(
        "REGRESSION" in w
        for c in result2.get("consider", [])
        for w in c.get("warnings", [])
    )
    assert has_regression_info or has_warning, (
        "Expected regression info in memory or warning on the suggestion"
    )


# ------------------------------------------------------------------
# Project context
# ------------------------------------------------------------------

def test_with_project_context(_patch_memory):
    """When a project context exists, it should appear in the result."""
    store: MemoryStore = _patch_memory

    ctx = CodebaseContext(
        project_id="test-proj",
        project_path="/tmp/test",
        language="python",
        structures_found=[
            StructureFound(type="hashmap", location="main.py", usage="cache"),
        ],
        patterns_found=[
            PatternFound(pattern="sliding-window", location="algo.py"),
        ],
        runtime_constraints="max memory 256MB",
    )
    store.set_context(ctx)

    result = plan_algorithm(
        problem="find contiguous subarray with max sum",
        structural_signals=["maximum sum contiguous subarray"],
        project_id="test-proj",
    )

    assert result["context"].get("project_id") == "test-proj"
    assert "hashmap" in result["context"].get("structures_in_use", [])


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------

def test_no_signals_no_structures():
    """With no signals or structures, should return empty results gracefully."""
    result = plan_algorithm(problem="some problem")
    assert result["matched_rules"] == []
    assert result["consider"] == []
    assert result["knowledge"] == {}
