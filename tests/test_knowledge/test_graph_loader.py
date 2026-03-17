# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for GraphKnowledgeLoader — verify graph mode matches JSON mode.

Uses Othrys's importer to populate a test DB, then runs the same assertions
as the JSON loader tests to prove both modes produce equivalent results.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import real_ladybug as kuzu

from mnemos.knowledge.loader import KnowledgeLoader
from mnemos.knowledge.graph_loader import GraphKnowledgeLoader

# We need Othrys's importer to populate the test DB
OTHRYS_SRC = Path("/Users/rezamalik/Repos/othrys/src")
MNEMOS_REPO = Path("/Users/rezamalik/Repos/mnemos-mcp")

# Add Othrys to path so we can use its importer
import sys
if str(OTHRYS_SRC) not in sys.path:
    sys.path.insert(0, str(OTHRYS_SRC))


@pytest.fixture(scope="module")
def graph_db(tmp_path_factory):
    """Populate a test DB using Othrys's importer."""
    from othrys.schema import init_db
    from othrys.importers import import_titan

    tmp = tmp_path_factory.mktemp("graph_test")
    db = init_db(tmp / "test.db")
    conn = kuzu.Connection(db)
    import_titan(MNEMOS_REPO, "mnemos", conn)
    return db, conn


@pytest.fixture(scope="module")
def graph_loader(graph_db):
    """GraphKnowledgeLoader backed by the test DB."""
    _, conn = graph_db
    return GraphKnowledgeLoader(conn)


@pytest.fixture(scope="module")
def json_loader():
    """Standard JSON KnowledgeLoader for comparison."""
    return KnowledgeLoader()


# ------------------------------------------------------------------
# Parity tests: graph loader produces same results as JSON loader
# ------------------------------------------------------------------

class TestGraphLoaderParity:

    def test_pattern_count_matches(self, graph_loader, json_loader):
        graph_patterns = graph_loader.get_all_patterns()
        json_patterns = json_loader.get_all_patterns()
        assert len(graph_patterns) == len(json_patterns)

    def test_structure_count_matches(self, graph_loader, json_loader):
        graph_structs = graph_loader.get_all_structures()
        json_structs = json_loader.get_all_structures()
        assert len(graph_structs) == len(json_structs)

    def test_get_pattern_by_id(self, graph_loader, json_loader):
        pat_g = graph_loader.get_pattern("two-pointer-convergent")
        pat_j = json_loader.get_pattern("two-pointer-convergent")
        assert pat_g is not None
        assert pat_j is not None
        assert pat_g["name"] == pat_j["name"]
        assert pat_g["structure_id"] == pat_j["structure_id"]
        assert pat_g["complexity"] == pat_j["complexity"]

    def test_get_pattern_not_found(self, graph_loader):
        assert graph_loader.get_pattern("nonexistent") is None

    def test_get_structure_by_id(self, graph_loader, json_loader):
        struct_g = graph_loader.get_structure("array")
        struct_j = json_loader.get_structure("array")
        assert struct_g is not None
        assert struct_j is not None
        assert struct_g["name"] == struct_j["name"]
        assert len(struct_g["patterns"]) == len(struct_j["patterns"])

    def test_get_alternatives(self, graph_loader, json_loader):
        alts_g = graph_loader.get_alternatives("two-pointer-convergent")
        alts_j = json_loader.get_alternatives("two-pointer-convergent")
        ids_g = set(a["id"] for a in alts_g)
        ids_j = set(a["id"] for a in alts_j)
        # Graph mode has bidirectional edges, so it may find more alternatives.
        # All JSON alternatives must be present in graph alternatives.
        assert ids_j.issubset(ids_g)

    def test_match_structural_signals(self, graph_loader, json_loader):
        signals = ["sorted input with pair satisfying arithmetic constraint"]
        matches_g = graph_loader.match_structural_signals(signals)
        matches_j = json_loader.match_structural_signals(signals)
        assert len(matches_g) == len(matches_j)
        if matches_g:
            assert matches_g[0]["rule"]["id"] == matches_j[0]["rule"]["id"]

    def test_filter_by_constraints(self, graph_loader, json_loader):
        patterns = [
            {"name": "test", "complexity": {"time": "O(n^2)", "space": "O(1)"}},
            {"name": "test2", "complexity": {"time": "O(n)", "space": "O(n)"}},
        ]
        constraints = {"n": 1_000_000}
        surv_g, filt_g = graph_loader.filter_by_constraints(patterns, constraints)
        surv_j, filt_j = json_loader.filter_by_constraints(patterns, constraints)
        assert len(surv_g) == len(surv_j)
        assert len(filt_g) == len(filt_j)

    def test_compact_index(self, graph_loader, json_loader):
        idx_g = graph_loader.get_compact_index()
        idx_j = json_loader.get_compact_index()
        assert len(idx_g) == len(idx_j)

    def test_max_feasible_complexity_rank(self, graph_loader, json_loader):
        for n in [100, 10_000, 1_000_000]:
            assert graph_loader.max_feasible_complexity_rank(n) == \
                   json_loader.max_feasible_complexity_rank(n)

    def test_get_complexity(self, graph_loader, json_loader):
        """Static reference data from complexities.json."""
        c_g = graph_loader.get_complexity("array", "access")
        c_j = json_loader.get_complexity("array", "access")
        assert c_g == c_j


# ------------------------------------------------------------------
# Tool tests in graph mode
# ------------------------------------------------------------------

class TestToolsGraphMode:

    def test_plan_algorithm_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.plan_algorithm import plan_algorithm

        result = plan_algorithm(
            problem="find two numbers that sum to target",
            structural_signals=[
                "Unsorted input with pair satisfying arithmetic constraint"
            ],
            conn=conn,
        )
        assert isinstance(result, dict)
        assert "matched_rules" in result
        assert len(result["matched_rules"]) > 0

    def test_review_complexity_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.review_complexity import review_complexity

        result = review_complexity(
            detected_pattern="nested-loop-search",
            detected_complexity="O(n^2)",
            constraints={"n": 1_000_000},
            conn=conn,
        )
        assert isinstance(result, dict)
        assert "feasibility" in result

    def test_suggest_refactor_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.suggest_refactor import suggest_refactor

        result = suggest_refactor(
            current_pattern="linear-search",
            current_complexity="O(n)",
            target_complexity="O(log n)",
            conn=conn,
        )
        assert isinstance(result, dict)
        assert "suggestions" in result

    def test_log_decision_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.log_decision import log_decision

        result = log_decision(
            mode="plan",
            problem="find two numbers that sum to target",
            pattern_chosen="hash-map-lookup",
            ds_chosen="hash-map",
            outcome="accepted",
            project_id="test-project",
            conn=conn,
        )
        assert isinstance(result, dict)
        assert result["logged"] is True
        assert "decision_id" in result

    def test_log_decision_with_regression_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.log_decision import log_decision

        result = log_decision(
            mode="review",
            problem="sort large dataset",
            pattern_chosen="bubble-sort",
            ds_chosen="array",
            outcome="regressed",
            project_id="test-project",
            regression_details="O(n^2) too slow for n=1M",
            conn=conn,
        )
        assert result["logged"] is True
        assert "regression_id" in result

    def test_log_decision_with_correction_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.log_decision import log_decision

        result = log_decision(
            mode="maintain",
            problem="lookup in sorted array",
            pattern_chosen="linear-search",
            ds_chosen="array",
            outcome="accepted",
            project_id="test-project",
            correction_details="linear-search -> binary-search: sorted input",
            conn=conn,
        )
        assert result["logged"] is True
        assert "correction_id" in result

    def test_bootstrap_context_graph(self, graph_db):
        _, conn = graph_db
        from mnemos.tools.bootstrap_context import bootstrap_context

        result = bootstrap_context(
            project_path="/tmp/graph-test",
            language="python",
            structures_found=[
                {"type": "array", "location": "main.py", "usage": "buffer"},
            ],
            conn=conn,
        )
        assert result["stored"] is True
        assert "project_id" in result


# ------------------------------------------------------------------
# GraphMemoryStore direct tests
# ------------------------------------------------------------------

class TestGraphMemoryStore:

    def test_log_and_retrieve_decision(self, graph_db):
        _, conn = graph_db
        from mnemos.memory.graph_store import GraphMemoryStore
        from mnemos.memory.schemas import Decision, DecisionMode, DecisionOutcome

        store = GraphMemoryStore(conn)
        decision = Decision(
            mode=DecisionMode.plan,
            problem_description="test problem",
            pattern_chosen="two-pointer-convergent",
            ds_chosen="array",
            outcome=DecisionOutcome.accepted,
            project_id="gms-test",
        )
        did = store.log_decision(decision)
        assert did == decision.id

        decisions = store.get_decisions(project_id="gms-test")
        assert len(decisions) >= 1
        found = [d for d in decisions if d.id == decision.id]
        assert len(found) == 1
        assert found[0].pattern_chosen == "two-pointer-convergent"

    def test_regression_roundtrip(self, graph_db):
        _, conn = graph_db
        from mnemos.memory.graph_store import GraphMemoryStore
        from mnemos.memory.schemas import Regression, Severity

        store = GraphMemoryStore(conn)
        reg = Regression(
            pattern="bubble-sort",
            ds="array",
            description="too slow at scale",
            severity=Severity.high,
            project_id="gms-test",
        )
        rid = store.add_regression(reg)
        assert rid == reg.id

        found = store.check_regression(pattern="bubble-sort", ds="array")
        assert found is not None
        assert found.description == "too slow at scale"

    def test_correction_roundtrip(self, graph_db):
        _, conn = graph_db
        from mnemos.memory.graph_store import GraphMemoryStore
        from mnemos.memory.schemas import Correction

        store = GraphMemoryStore(conn)
        corr = Correction(
            original_pattern="linear-search",
            corrected_pattern="binary-search",
            reason="input was sorted",
            project_id="gms-test",
        )
        cid = store.add_correction(corr)
        assert cid == corr.id

        corrections = store.get_corrections(project_id="gms-test")
        assert len(corrections) >= 1
        found = [c for c in corrections if c.id == corr.id]
        assert len(found) == 1
        assert found[0].reason == "input was sorted"

    def test_context_roundtrip(self, graph_db):
        _, conn = graph_db
        from mnemos.memory.graph_store import GraphMemoryStore
        from mnemos.memory.schemas import CodebaseContext, StructureFound

        store = GraphMemoryStore(conn)
        ctx = CodebaseContext(
            project_id="gms-ctx-test",
            project_path="/tmp/gms-test",
            language="python",
            structures_found=[
                StructureFound(type="array", location="main.py", usage="buffer"),
            ],
        )
        pid = store.set_context(ctx)
        assert pid == "gms-ctx-test"

        loaded = store.get_context("gms-ctx-test")
        assert loaded is not None
        assert loaded.language == "python"
        assert len(loaded.structures_found) == 1
