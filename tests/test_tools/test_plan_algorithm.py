# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for the retrofitted plan_algorithm tool (story-133fad58).

plan_algorithm now rides the Shape-C engine: ``matched_signal_ids`` -> one
``kb.hydrate`` -> complexity-feasibility EXCLUSION (``filter_by_constraints``) ->
reason over each retrieved pattern's OWN fields. The prose ``structural_signals``
substring path (``match_structural_signals``) is gone from the tool.

Coverage:
  * the NEW output contract (matched_rules absent; recommendations/retrieval_state/
    unmatched/dangling/filtered_out present; integer votes only, no float);
  * RED anchors — (a) a problem the matcher returns EMPTY for now returns the gold
    algorithm; (b) a complexity-infeasible pattern is EXCLUDED into filtered_out;
  * the four-state fail-closed envelope (no husk on no_match/dangling);
  * empirical memory KEPT (check_regression + project context still invoked);
  * determinism (identical matched_signal_ids -> identical ranking + votes);
  * BAR-1 (recall@10 through plan_algorithm's hydrate path >= the S0 locked floor,
    stratified) and BAR-2 (the before/after delta over the matcher baseline).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from mnemos.knowledge.loader import (
    DANGLING,
    HIT,
    LOW_CONFIDENCE,
    NO_MATCH,
    KnowledgeLoader,
    _rank,
    _signal_id,
)
from mnemos.memory.store import MemoryStore
from mnemos.memory.schemas import (
    CodebaseContext,
    PatternFound,
    Regression,
    Severity,
    StructureFound,
)
from mnemos.tools.plan_algorithm import plan_algorithm

# --- frozen gmetric substrate for BAR-1 / BAR-2 (mirrors test_retrieval_bar1) ---
_GMETRIC = Path(__file__).resolve().parents[1] / "data" / "gmetric"
if str(_GMETRIC) not in sys.path:
    sys.path.insert(0, str(_GMETRIC))
os.environ["MNEMOS_GMETRIC_VERSION"] = "v2"  # set before importing grade

import grade  # noqa: E402  (path-injected frozen grader, reused verbatim, v2-selected)

MATCHES = json.loads((_GMETRIC / "mnemos_matches_v2.json").read_text(encoding="utf-8"))["matches"]
LEGS = json.loads((_GMETRIC / "locked_legs_v2.json").read_text(encoding="utf-8"))

# Two signals that co-vote dijkstra to a HIT (shared with test_signal_engine).
_DIJKSTRA_SIGS = [
    _signal_id("weighted-graph-shortest-path"),
    _signal_id("greedy-nearest-unvisited-expansion"),
]
# The PB prose the retired matcher scored 0 on (frozen benchmark P15 query).
_PB_PROSE = "Find the cheapest route between two cities where each road has a positive travel cost."


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    """Hermetic memory: the shared singleton points at a temp dir for every test."""
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store):
        yield temp_store


@pytest.fixture(scope="module")
def kb() -> KnowledgeLoader:
    return KnowledgeLoader()


def _ids(result: dict) -> list[str]:
    return [r["pattern_id"] for r in result["recommendations"]]


# ==========================================================================
# Output contract — matched_rules gone; the new keys present; no float
# ==========================================================================

class TestOutputContract:
    def test_new_contract_keys_present_matched_rules_absent(self):
        res = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS)
        assert "matched_rules" not in res           # rule-shaped output retired
        assert "consider" not in res and "knowledge" not in res  # old surfaces gone
        for key in ("recommendations", "filtered_out", "retrieval_state",
                    "unmatched", "dangling", "context", "memory"):
            assert key in res, f"missing contract key {key}"

    def test_recommendation_carries_own_fields_and_integer_votes(self):
        res = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["retrieval_state"] == HIT
        top = res["recommendations"][0]
        assert top["rank"] == 1
        # reasoning is over the pattern's OWN fields
        assert set(top["fit"]) == {"complexity", "applies_when", "avoid_when", "constraints"}
        # votes are transparent integers, never a tuned float score
        r = top["retrieval"]
        assert isinstance(r["score"], int) and isinstance(r["direct_votes"], int)
        assert all(not isinstance(v, float) for v in r.values())

    def test_structural_signals_param_is_retired_no_alias_shim(self):
        # the prose param is gone; passing it must fail loud, not silently alias.
        with pytest.raises(TypeError):
            plan_algorithm(problem="x", structural_signals=["sorted input with pair"])


# ==========================================================================
# Four-state fail-closed envelope — never a husk
# ==========================================================================

class TestRetrievalStates:
    def test_hit_returns_ranked_recommendations(self):
        res = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["retrieval_state"] == HIT
        assert "dijkstra" in _ids(res)

    def test_low_confidence_single_vote_still_surfaces(self):
        res = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS[:1])
        assert res["retrieval_state"] == LOW_CONFIDENCE
        assert res["recommendations"]                       # surfaced, not empty

    def test_no_match_abstains_empty_with_populated_envelope(self):
        res = plan_algorithm(problem="x", matched_signal_ids=["sig-does-not-exist"])
        assert res["retrieval_state"] == NO_MATCH
        assert res["recommendations"] == [] and res["filtered_out"] == []   # no husk
        assert res["unmatched"] == ["sig-does-not-exist"]

    def test_empty_input_abstains_no_match(self):
        res = plan_algorithm(problem="x", matched_signal_ids=[])
        assert res["retrieval_state"] == NO_MATCH
        assert res["recommendations"] == []

    def test_dangling_abstains_empty_with_populated_envelope(self):
        """DANGLING: every hydrated id fails to resolve (constructed fixture, per the
        engine's own dangling test — unreachable on the real corpus)."""
        loader = KnowledgeLoader()
        ghost = "sig-ghost0000000"
        loader._signal_index[ghost] = {
            "signal_id": ghost, "signal_text": "ghost", "pattern_ids": ["__absent__"],
        }
        with patch("mnemos.tools._shared.knowledge", loader):
            res = plan_algorithm(problem="x", matched_signal_ids=[ghost])
        assert res["retrieval_state"] == DANGLING
        assert res["recommendations"] == [] and res["filtered_out"] == []
        assert "__absent__" in res["dangling"]


# ==========================================================================
# RED anchors — the before/after that justifies the retrofit
# ==========================================================================

class TestRedAnchors:
    def test_a_matcher_empty_now_returns_gold(self):
        """(a) The legacy matcher scored 0 on this PB prose; the retrofit, given the
        recognised signal ids, returns the gold algorithm (dijkstra). BEFORE=empty is
        now frozen provenance -- the matcher was deleted at S6 (story-24ba71ef) and
        P15's covered@10 is 0 in the pinned baseline (baseline_matcher_pinned_v2.json),
        not a live assert against a deleted method."""
        res = plan_algorithm(problem=_PB_PROSE, matched_signal_ids=MATCHES["P15"])
        assert res["retrieval_state"] == HIT                            # AFTER: hit
        ids = _ids(res)
        assert "dijkstra" in ids and "bellman-ford" in ids             # gold recovered

    def test_b_infeasible_pattern_excluded_into_filtered_out(self, kb: KnowledgeLoader):
        """(b) A pattern whose OWN time complexity exceeds the guideline for n is
        EXCLUDED from recommendations and surfaced in filtered_out (the Mnemos gate).
        Corpus-driven: pick a genuinely-infeasible pattern rather than hardcode one."""
        n = 1_000_000
        max_rank = kb.max_feasible_complexity_rank(n)
        victim = next(
            p for p in kb.get_all_patterns()
            if (t := (p.get("complexity") or {}).get("time", ""))
            and _rank(t) > max_rank and p.get("structural_signals")
        )
        sig = _signal_id(victim["structural_signals"][0])
        res = plan_algorithm(problem="big input", matched_signal_ids=[sig],
                             constraints={"n": n})
        rec_ids = _ids(res)
        filt = {f["pattern_id"]: f["reason"] for f in res["filtered_out"]}
        assert victim["id"] in filt, f"{victim['id']} should be excluded for n={n:,}"
        assert victim["id"] not in rec_ids                             # excluded, not demoted
        assert str(n) in filt[victim["id"]] or "infeasible" in filt[victim["id"]]

    def test_faster_first_rerank_under_size_constraint(self):
        """Survivors are re-ranked faster-first when a size constraint governs
        (non-decreasing time-complexity rank); no size constraint -> hydrate order."""
        res = plan_algorithm(problem="edit distance",
                             matched_signal_ids=MATCHES["P32"], constraints={"n": 1_000_000})
        ranks = [_rank(r["fit"]["complexity"].get("time", "")) for r in res["recommendations"]]
        assert ranks == sorted(ranks), f"survivors not faster-first: {ranks}"

    def test_no_constraint_preserves_hydrate_vote_order(self, kb: KnowledgeLoader):
        res = plan_algorithm(problem="edit distance", matched_signal_ids=MATCHES["P32"])
        hydrate_order = [p["id"] for p in kb.hydrate(MATCHES["P32"], k=10).patterns]
        assert _ids(res) == hydrate_order


# ==========================================================================
# Empirical memory — KEPT (check_regression + project context still invoked)
# ==========================================================================

class TestEmpiricalMemoryKept:
    def test_regression_annotation_surfaces(self, _patch_memory):
        store: MemoryStore = _patch_memory
        res = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS)
        top = res["recommendations"][0]
        store.add_regression(Regression(
            pattern=top["pattern_id"], ds=top["structure_id"],
            description="regressed on dense graphs", severity=Severity.high,
            project_id="default",
        ))
        res2 = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS)
        regs = res2["memory"].get("regressions", [])
        assert any(r["pattern"] == top["pattern_id"] for r in regs)
        # a memory annotation NEVER re-orders the recommendations
        assert _ids(res2) == _ids(res)

    def test_project_context_surfaces(self, _patch_memory):
        store: MemoryStore = _patch_memory
        store.set_context(CodebaseContext(
            project_id="proj-x", project_path="/tmp/x", language="python",
            structures_found=[StructureFound(type="hashmap", location="m.py", usage="cache")],
            patterns_found=[PatternFound(pattern="sliding-window", location="a.py")],
            runtime_constraints="max memory 256MB",
        ))
        res = plan_algorithm(problem="shortest path", matched_signal_ids=_DIJKSTRA_SIGS,
                             project_id="proj-x")
        assert res["context"]["project_id"] == "proj-x"
        assert "hashmap" in res["context"]["structures_in_use"]


# ==========================================================================
# Determinism — identical matched_signal_ids -> identical ranking + votes
# ==========================================================================

class TestDeterminism:
    def test_identical_input_identical_ranking_and_votes(self):
        a = plan_algorithm(problem="p", matched_signal_ids=_DIJKSTRA_SIGS)
        b = plan_algorithm(problem="p", matched_signal_ids=_DIJKSTRA_SIGS)
        assert _ids(a) == _ids(b)
        assert [r["retrieval"] for r in a["recommendations"]] == \
               [r["retrieval"] for r in b["recommendations"]]

    def test_fresh_loader_matches_singleton(self):
        fresh = KnowledgeLoader()
        with patch("mnemos.tools._shared.knowledge", fresh):
            a = plan_algorithm(problem="p", matched_signal_ids=_DIJKSTRA_SIGS)
        b = plan_algorithm(problem="p", matched_signal_ids=_DIJKSTRA_SIGS)
        assert _ids(a) == _ids(b)

    def test_ranking_and_votes_stable_across_pythonhashseed(self):
        """A PYTHONHASHSEED flip must not move the ranking or the votes (real proof
        in fresh subprocesses, not just the by-construction argument)."""
        import subprocess

        sigs = json.dumps(_DIJKSTRA_SIGS)
        snippet = (
            "import json;"
            "from mnemos.tools.plan_algorithm import plan_algorithm as f;"
            f"r=f(problem='p', matched_signal_ids=json.loads('{sigs}'), k=10);"
            "print(json.dumps([(x['pattern_id'], x['retrieval']) for x in r['recommendations']]))"
        )
        env_base = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
        outs = []
        for seed in ("0", "1", "12345"):
            res = subprocess.run(
                [sys.executable, "-c", snippet],
                capture_output=True, text=True, env={**env_base, "PYTHONHASHSEED": seed},
            )
            assert res.returncode == 0, res.stderr
            outs.append(res.stdout.strip())
        assert len(set(outs)) == 1, f"ranking/votes moved across PYTHONHASHSEED: {outs}"


# ==========================================================================
# BAR-1 (recall@10 through plan_algorithm's hydrate path) + BAR-2 (before/after)
# ==========================================================================

def _rank_via_plan_algorithm(loader, query):
    """grade.grade method_fn: frozen query -> ranked ids via plan_algorithm.

    Resolves the query to its problem id, feeds the frozen recognised signal ids
    (the same substrate BAR-1's engine harness uses) through plan_algorithm, and
    returns the ranked recommendation ids. No constraints -> the tool preserves
    hydrate's vote order, so this measures the retrofit's retrieval path end to end.
    """
    q2pid = {tuple(p["query"]): p["id"]
             for p in json.loads((_GMETRIC / "problems_blind_v2.json").read_text(encoding="utf-8"))["problems"]}
    pid = q2pid[tuple(query)]
    res = plan_algorithm(problem="", matched_signal_ids=MATCHES[pid], k=10)
    return [r["pattern_id"] for r in res["recommendations"]]


class TestBar1ThroughPlanAlgorithm:
    def test_substrate_frozen(self):
        grade._verify_substrate()  # fail closed on any corpus/benchmark drift

    def test_recall_at_10_reproduces_engine_floor_stratified(self):
        """BAR-1: recall@10 through plan_algorithm == the S0-locked engine floor
        (74/77), stratified per class — the win lands in the PB/TK problem-language
        classes the matcher scored 0 on (never a pooled mean)."""
        core = grade.grade(_rank_via_plan_algorithm, "plan_algorithm_hydrate")
        assert core["denominator_E_golds"] == 77
        assert core["covered"]["10"] >= LEGS["LEG_2_design_works_floor"]["engine_min_covered_at_10"]
        assert core["recall"]["10"] >= LEGS["LEG_2_design_works_floor"]["floor"]
        by = core["by_qclass"]
        assert by["PB"]["10"]["covered"] >= 20      # matcher: 0/25
        assert by["TK"]["10"]["covered"] >= 20      # matcher: 0/22
        assert by["PA"]["10"]["covered"] >= 22      # not collapsed

    def test_top10_identical_to_engine_per_problem(self):
        """Reproduced, not re-derived: the tool path yields the engine's own top-10
        for every problem (plan_algorithm just wraps the same hydrate call)."""
        import mnemos_engine_bench as eng
        tool = grade.grade(_rank_via_plan_algorithm, "tool")
        engine = grade.grade(eng.rank_engine, "engine")
        assert all(tool["per_problem"][p]["ranked_top10"] == engine["per_problem"][p]["ranked_top10"]
                   for p in tool["per_problem"])

    def test_bar2_before_after_delta_over_matcher_baseline(self):
        """BAR-2: the before/after delta. BEFORE = the pinned matcher baseline
        (== the pre-edit plan_algorithm, which merely wrapped the matcher): 27/77,
        PB=TK=0. The matcher was deleted at S6, so BEFORE is read from the frozen pin,
        not recomputed. AFTER = the hydrate path: >=74/77 with PB/TK recovered."""
        before = grade.load_pinned_baseline()
        after = grade.grade(_rank_via_plan_algorithm, "plan_algorithm_hydrate")
        assert before["covered"]["10"] == 27                        # frozen matcher baseline
        assert before["by_qclass"]["PB"]["10"]["covered"] == 0
        assert before["by_qclass"]["TK"]["10"]["covered"] == 0
        delta = after["covered"]["10"] - before["covered"]["10"]
        assert delta >= 40, f"before/after delta only +{delta}"      # measured +47
