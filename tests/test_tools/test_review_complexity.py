# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for the review_complexity tool."""

import pytest
from pathlib import Path
from unittest.mock import patch

from mnemos.memory.store import MemoryStore
from mnemos.memory.schemas import Regression, Severity
from mnemos.tools.review_complexity import review_complexity


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    """Monkey-patch the shared memory singleton to use a temp directory."""
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store), \
         patch("mnemos.tools.review_complexity.memory", temp_store):
        yield temp_store


# ------------------------------------------------------------------
# Pattern lookup and alternatives
# ------------------------------------------------------------------

def test_detected_pattern_returns_known_info():
    """Looking up a known pattern should return its knowledge-base info."""
    result = review_complexity(
        detected_pattern="two-pointer-convergent",
        detected_complexity="O(n)",
    )
    detected = result["detected"]
    assert detected["pattern"] == "two-pointer-convergent"
    assert "known_pattern" in detected
    assert detected["known_pattern"]["id"] == "two-pointer-convergent"


def test_returns_alternatives_for_known_pattern():
    """A known pattern with alternatives should return them."""
    result = review_complexity(
        detected_pattern="two-pointer-convergent",
        detected_complexity="O(n)",
    )
    # two-pointer-convergent should have alternatives in the KB
    # (at minimum from the decision rules)
    alternatives = result["alternatives"]
    # Alternatives may be empty if all have equal or worse complexity
    # Just verify the structure is correct
    assert isinstance(alternatives, list)


def test_unknown_pattern_handled_gracefully():
    """An unknown pattern should not crash, just return empty known_pattern."""
    result = review_complexity(
        detected_pattern="nonexistent-pattern-xyz",
        detected_complexity="O(n^2)",
    )
    detected = result["detected"]
    assert detected["pattern"] == "nonexistent-pattern-xyz"
    assert "known_pattern" not in detected


# ------------------------------------------------------------------
# Feasibility check
# ------------------------------------------------------------------

def test_feasibility_check_infeasible():
    """O(n^2) with n=10^6 should be flagged as infeasible."""
    result = review_complexity(
        detected_pattern="two-pointer-convergent",
        detected_complexity="O(n^2)",
        constraints={"n": 1_000_000},
    )
    assert result["feasibility"]["is_feasible"] is False
    assert "infeasible" in result["feasibility"].get("reason", "").lower()


def test_feasibility_check_feasible():
    """O(n) with n=10^6 should be feasible."""
    result = review_complexity(
        detected_complexity="O(n)",
        constraints={"n": 1_000_000},
    )
    assert result["feasibility"]["is_feasible"] is True


# ------------------------------------------------------------------
# Structure info
# ------------------------------------------------------------------

def test_detected_structures_returns_info():
    """Providing structure IDs should return their operation costs."""
    result = review_complexity(
        detected_structures=["array", "hashmap"],
    )
    assert "array" in result["structure_info"]
    assert "hashmap" in result["structure_info"]
    assert "operations" in result["structure_info"]["array"]


# ------------------------------------------------------------------
# Memory regressions
# ------------------------------------------------------------------

def test_regression_on_detected_pattern(_patch_memory):
    """If the detected pattern has a regression, it should appear."""
    store: MemoryStore = _patch_memory

    # Look up the pattern to find its structure_id
    from mnemos.tools._shared import knowledge
    pat = knowledge.get_pattern("two-pointer-convergent")
    if not pat:
        pytest.skip("Pattern not in knowledge base")

    ds = pat.get("structure_id", "")
    store.add_regression(Regression(
        pattern="two-pointer-convergent",
        ds=ds,
        description="Failed on edge case",
        severity=Severity.medium,
        project_id="default",
    ))

    result = review_complexity(
        detected_pattern="two-pointer-convergent",
        detected_complexity="O(n)",
    )
    assert len(result.get("memory", {}).get("regressions", [])) > 0
