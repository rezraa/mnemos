# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for KnowledgeLoader."""

import pytest

from mnemos.knowledge.loader import KnowledgeLoader, _rank


@pytest.fixture(scope="module")
def loader() -> KnowledgeLoader:
    """Shared loader backed by the real knowledge base."""
    return KnowledgeLoader()


# ------------------------------------------------------------------
# Basic loading
# ------------------------------------------------------------------

def test_loads_structures(loader: KnowledgeLoader):
    structures = loader.get_all_structures()
    assert len(structures) > 0, "Expected at least one structure in the knowledge base"


def test_loads_patterns(loader: KnowledgeLoader):
    patterns = loader.get_all_patterns()
    assert len(patterns) > 0, "Expected at least one pattern in the knowledge base"


# ------------------------------------------------------------------
# match_structural_signals unit tests RETIRED at S6 (story-24ba71ef)
# ------------------------------------------------------------------
# The legacy exact-substring matcher was deleted from KnowledgeLoader; the
# signal-index hydrate engine is the sole retrieval path (covered by
# test_signal_engine.py and the tool tests). The five tests here exercised the
# deleted method only. Coverage delta: -5 matcher-behaviour tests; the KEPT
# primitives get_alternatives (test_get_alternatives, below) and
# filter_by_constraints (below) retain their own tests -- no other coverage lost.


# ------------------------------------------------------------------
# filter_by_constraints
# ------------------------------------------------------------------

def test_filter_by_constraints_input_size(loader: KnowledgeLoader):
    """With n=10^6, O(n^2) patterns should be filtered out."""
    all_patterns = loader.get_all_patterns()
    surviving, removed = loader.filter_by_constraints(
        all_patterns, {"input_size": 1_000_000},
    )

    assert len(removed) > 0, "Some patterns should be filtered for n=10^6"
    assert len(surviving) < len(all_patterns)

    # Verify no surviving pattern has infeasible complexity
    from mnemos.knowledge.loader import _COMPLEXITY_RANK
    max_allowed_rank = _COMPLEXITY_RANK.index("O(n log n)")
    for pat in surviving:
        time_str = pat.get("complexity", {}).get("time", "")
        if time_str:
            rank = _rank(time_str)
            assert rank <= max_allowed_rank, (
                f"Pattern {pat['id']} with time={time_str} should have been filtered"
            )


def test_filter_by_constraints_space(loader: KnowledgeLoader):
    """Space constraint should filter patterns exceeding it."""
    all_patterns = loader.get_all_patterns()
    surviving, removed = loader.filter_by_constraints(
        all_patterns, {"space": "O(1)"},
    )
    for pat in surviving:
        space_str = pat.get("complexity", {}).get("space", "")
        if space_str:
            assert _rank(space_str) <= _rank("O(1)"), (
                f"Pattern {pat['id']} with space={space_str} should have been filtered"
            )


def test_filter_by_constraints_target_complexity(loader: KnowledgeLoader):
    """Target complexity should filter patterns exceeding it."""
    all_patterns = loader.get_all_patterns()
    surviving, removed = loader.filter_by_constraints(
        all_patterns, {"target_complexity": "O(n)"},
    )
    for pat in surviving:
        time_str = pat.get("complexity", {}).get("time", "")
        if time_str:
            assert _rank(time_str) <= _rank("O(n)"), (
                f"Pattern {pat['id']} with time={time_str} should have been filtered"
            )


def test_filter_preserves_all_when_no_constraints(loader: KnowledgeLoader):
    """Empty constraints should not filter anything."""
    all_patterns = loader.get_all_patterns()
    surviving, removed = loader.filter_by_constraints(all_patterns, {})
    assert len(surviving) == len(all_patterns)
    assert len(removed) == 0


# ------------------------------------------------------------------
# Batch retrieval
# ------------------------------------------------------------------

def test_get_structures_by_ids(loader: KnowledgeLoader):
    results = loader.get_structures_by_ids(["array", "hashmap"])
    assert len(results) == 2
    ids = {s["id"] for s in results}
    assert ids == {"array", "hashmap"}


def test_get_structures_by_ids_partial(loader: KnowledgeLoader):
    """Non-existent IDs should be silently skipped."""
    results = loader.get_structures_by_ids(["array", "nonexistent_12345"])
    assert len(results) == 1
    assert results[0]["id"] == "array"


# ------------------------------------------------------------------
# Compact index
# ------------------------------------------------------------------

def test_get_compact_index(loader: KnowledgeLoader):
    index = loader.get_compact_index()
    assert len(index) > 0
    first = index[0]
    assert "id" in first
    assert "name" in first
    assert "structure" in first
    assert "structural_signals" in first
    # Should NOT have full pattern details
    assert "applies_when" not in first
    assert "alternatives" not in first


# ------------------------------------------------------------------
# Direct lookups (unchanged)
# ------------------------------------------------------------------

def test_get_complexity(loader: KnowledgeLoader):
    result = loader.get_complexity("array", "access")
    assert result is not None
    assert result["data_structure"] == "array"
    assert result["operation"] == "access"
    assert "complexity" in result


def test_get_alternatives(loader: KnowledgeLoader):
    patterns = loader.get_all_patterns()
    pattern_with_alts = None
    for p in patterns:
        if p.get("alternatives"):
            pattern_with_alts = p
            break

    assert pattern_with_alts is not None, "Expected at least one pattern with alternatives"

    alts = loader.get_alternatives(pattern_with_alts["id"])
    assert len(alts) > 0
    first_alt = alts[0]
    assert "id" in first_alt
    assert "name" in first_alt
    assert "when_better" in first_alt


def test_get_structure_by_id(loader: KnowledgeLoader):
    result = loader.get_structure("array")
    assert result is not None
    assert result["id"] == "array"
    assert "patterns" in result

    assert loader.get_structure("nonexistent_ds_12345") is None


def test_get_pattern_by_id(loader: KnowledgeLoader):
    patterns = loader.get_all_patterns()
    first_id = patterns[0]["id"]

    result = loader.get_pattern(first_id)
    assert result is not None
    assert result["id"] == first_id
    assert "structure_id" in result

    assert loader.get_pattern("nonexistent_pattern_12345") is None


# ------------------------------------------------------------------
# max_feasible_complexity_rank
# ------------------------------------------------------------------

def test_max_feasible_complexity_rank(loader: KnowledgeLoader):
    """Large n should constrain to fast complexities."""
    from mnemos.knowledge.loader import _COMPLEXITY_RANK

    rank_for_million = loader.max_feasible_complexity_rank(1_000_000)
    # Should allow at most O(n log n) for n=10^6
    assert rank_for_million <= _COMPLEXITY_RANK.index("O(n log n)")

    rank_for_small = loader.max_feasible_complexity_rank(10)
    # Should allow exponential for very small n
    assert rank_for_small >= _COMPLEXITY_RANK.index("O(2^n)")
