# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for the retrofitted review_complexity tool (story-824571cd, council f1b39fbd S4).

review_complexity now rides the Shape-C engine: it reasons the FEASIBILITY of the
agent's OWN detected complexity against constraints AND hydrates ``matched_signal_ids``
-> one ``kb.hydrate`` -> complexity-feasibility EXCLUSION (``filter_by_constraints``)
-> reasons the surviving candidates (the "better options") over each pattern's OWN
fields. The old exact-id ``get_pattern``/``get_alternatives`` husk — ``{is_feasible:
true}`` and empty ``alternatives`` whenever ``detected_pattern`` was not a verbatim
corpus id — is gone.

Coverage:
  * the NEW output contract (feasibility{is_feasible,reason}; alternatives with own-
    field fit; retrieval_state/unmatched/dangling/filtered_out present; int votes);
  * RED anchor / BAR-2 — the canonical husk ({is_feasible:true}+nothing) now returns
    a populated feasibility{is_feasible,reason} + non-empty alternatives (before/after
    delta over the pinned pre-edit output);
  * the four-state fail-closed envelope — abstention keeps feasibility/structure/
    memory (retrieval-independent), never a husk;
  * the complexity-feasibility gate (infeasible candidate excluded into filtered_out;
    faster-first re-rank under a size constraint; improvement annotation);
  * empirical memory KEPT (check_regression on the detected pattern still invoked,
    never re-orders); structure_info KEPT;
  * determinism (identical input -> identical output; fresh loader; PYTHONHASHSEED);
  * BAR-1 reproduced through review_complexity's own hydrate path (== engine order).
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
    Regression,
    Severity,
    StructureFound,
)
from mnemos.tools.review_complexity import review_complexity

# --- frozen gmetric substrate (shared with test_plan_algorithm / test_retrieval_bar1) ---
_GMETRIC = Path(__file__).resolve().parents[1] / "data" / "gmetric"
if str(_GMETRIC) not in sys.path:
    sys.path.insert(0, str(_GMETRIC))
os.environ["MNEMOS_GMETRIC_VERSION"] = "v2"

MATCHES = json.loads((_GMETRIC / "mnemos_matches_v2.json").read_text(encoding="utf-8"))["matches"]
BAR2_PIN = json.loads((_GMETRIC / "review_complexity_bar2_pin.json").read_text(encoding="utf-8"))

# Two signals that co-vote the dijkstra graph family to a HIT.
_DIJKSTRA_SIGS = [
    _signal_id("weighted-graph-shortest-path"),
    _signal_id("greedy-nearest-unvisited-expansion"),
]


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    """Hermetic memory: the shared singleton points at a temp dir for every test."""
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store):
        yield temp_store


@pytest.fixture(scope="module")
def kb() -> KnowledgeLoader:
    return KnowledgeLoader()


def _alt_ids(result: dict) -> list[str]:
    return [a["pattern_id"] for a in result["alternatives"]]


# ==========================================================================
# Output contract — husk gone; the new keys present; own-field fit; int votes
# ==========================================================================

class TestOutputContract:
    def test_new_contract_keys_present(self):
        res = review_complexity(detected_pattern="nested-loop", detected_complexity="O(n^2)",
                                matched_signal_ids=_DIJKSTRA_SIGS, constraints={"n": 1_000_000})
        for key in ("detected", "feasibility", "alternatives", "filtered_out",
                    "structure_info", "retrieval_state", "unmatched", "dangling",
                    "context", "memory", "constraints_analyzed"):
            assert key in res, f"missing contract key {key}"
        # the retired rule-shaped surfaces are gone
        assert "known_pattern" not in res["detected"]
        assert "matched_rules" not in res and "consider" not in res

    def test_alternative_carries_own_fields_and_integer_votes(self):
        res = review_complexity(detected_pattern="nested-loop", detected_complexity="O(n^2)",
                                matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["retrieval_state"] == HIT
        top = res["alternatives"][0]
        assert top["rank"] == 1
        # reasoning is over the pattern's OWN fields
        assert set(top["fit"]) == {"complexity", "use_when", "avoid_when", "constraints"}
        # votes are transparent integers, never a tuned float score
        r = top["retrieval"]
        assert isinstance(r["score"], int) and isinstance(r["direct_votes"], int)
        assert all(not isinstance(v, float) for v in r.values())

    def test_detected_echo_kept(self):
        res = review_complexity(detected_pattern="nested-loop", detected_structures=["array"],
                                detected_complexity="O(n^2)", matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["detected"] == {"pattern": "nested-loop", "structures": ["array"],
                                   "complexity": "O(n^2)"}


# ==========================================================================
# RED anchor + BAR-2 — the before/after that justifies the retrofit
# ==========================================================================

class TestRedAnchorAndBar2:
    def test_bar2_pin_captured_the_husk(self):
        """BAR-2 BEFORE (pinned pre-edit output): the canonical husk is
        {is_feasible:true} with NO reason and EMPTY alternatives; even the infeasible
        case surfaced no better options."""
        a = BAR2_PIN["husk_feasible_no_constraints"]
        assert a["feasibility"] == {"is_feasible": True}      # is_feasible:true and...
        assert a["alternatives"] == []                        # ...nothing
        b = BAR2_PIN["husk_infeasible_no_alts"]
        assert b["alternatives"] == []                        # no better options, even infeasible

    def test_red_canonical_husk_now_populated(self):
        """RED: the exact husk input ({is_feasible:true}+nothing) now returns a
        populated feasibility{is_feasible,reason} + non-empty alternatives reasoned
        over their own fields. Same detected inputs as the pin's case A, plus the
        recognised signal ids the retrofit adds."""
        res = review_complexity(detected_pattern="two_pointer", detected_structures=["array"],
                                detected_complexity="O(n)", matched_signal_ids=_DIJKSTRA_SIGS)
        # feasibility is now populated WITH a reason (the pin had is_feasible:true, no reason)
        assert res["feasibility"]["is_feasible"] is True
        assert res["feasibility"]["reason"]                    # non-empty reason string
        assert "reason" not in BAR2_PIN["husk_feasible_no_constraints"]["feasibility"]
        # alternatives are non-empty retrieved candidates, each reasoned over own fields
        assert res["alternatives"]
        assert all(set(a["fit"]) == {"complexity", "use_when", "avoid_when", "constraints"}
                   for a in res["alternatives"])

    def test_bar2_delta_alternatives_before_zero_after_nonzero(self):
        """BAR-2 delta asserted: BEFORE alternatives==0 (both pinned husks); AFTER,
        with the recognised signals, alternatives>0."""
        before = len(BAR2_PIN["husk_infeasible_no_alts"]["alternatives"])
        after = review_complexity(detected_pattern="nested_loop_pair_search",
                                  detected_structures=["array"], detected_complexity="O(n^2)",
                                  matched_signal_ids=_DIJKSTRA_SIGS, constraints={"n": 1_000_000})
        assert before == 0
        assert len(after["alternatives"]) >= 1
        # and every surfaced candidate is a genuine improvement over the infeasible O(n^2)
        assert all("improvement" in a for a in after["alternatives"])


# ==========================================================================
# Feasibility — reasons the agent's OWN detected complexity vs constraints
# ==========================================================================

class TestFeasibility:
    def test_infeasible_detected_complexity_has_reason(self):
        res = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=_DIJKSTRA_SIGS,
                                constraints={"n": 1_000_000})
        assert res["feasibility"]["is_feasible"] is False
        assert "infeasible" in res["feasibility"]["reason"].lower()

    def test_feasible_detected_complexity_has_reason(self):
        res = review_complexity(detected_complexity="O(n)", matched_signal_ids=_DIJKSTRA_SIGS,
                                constraints={"n": 1_000_000})
        assert res["feasibility"]["is_feasible"] is True
        assert "1,000,000" in res["feasibility"]["reason"]

    def test_no_constraint_not_flagged_but_reasoned(self):
        res = review_complexity(detected_complexity="O(n)", matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["feasibility"]["is_feasible"] is True
        assert res["feasibility"]["reason"]

    def test_no_detected_complexity_empty_feasibility(self):
        """Honest empty: nothing to assess -> empty feasibility (not a fabricated True)."""
        res = review_complexity(detected_structures=["array"], matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["feasibility"] == {}


# ==========================================================================
# The complexity-feasibility gate — exclusion, faster-first, improvement
# ==========================================================================

class TestGate:
    def test_infeasible_candidate_excluded_into_filtered_out(self, kb: KnowledgeLoader):
        """A retrieved candidate whose OWN time complexity exceeds the guideline for n
        is EXCLUDED from alternatives and surfaced in filtered_out. Corpus-driven:
        pick a genuinely-infeasible pattern rather than hardcode one."""
        n = 1_000_000
        max_rank = kb.max_feasible_complexity_rank(n)
        victim = next(
            p for p in kb.get_all_patterns()
            if (t := (p.get("complexity") or {}).get("time", ""))
            and _rank(t) > max_rank and p.get("structural_signals")
        )
        sig = _signal_id(victim["structural_signals"][0])
        res = review_complexity(detected_complexity="O(n^3)", matched_signal_ids=[sig],
                                constraints={"n": n})
        filt = {f["pattern_id"]: f["reason"] for f in res["filtered_out"]}
        assert victim["id"] in filt, f"{victim['id']} should be excluded for n={n:,}"
        assert victim["id"] not in _alt_ids(res)              # excluded, not surfaced
        assert str(n) in filt[victim["id"]] or "infeasible" in filt[victim["id"]]

    def test_faster_first_rerank_under_size_constraint(self):
        res = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=_DIJKSTRA_SIGS,
                                constraints={"n": 1_000_000})
        ranks = [_rank(a["fit"]["complexity"].get("time", "")) for a in res["alternatives"]]
        assert ranks == sorted(ranks), f"survivors not faster-first: {ranks}"

    def test_no_constraint_preserves_hydrate_vote_order(self, kb: KnowledgeLoader):
        res = review_complexity(matched_signal_ids=_DIJKSTRA_SIGS)
        hydrate_order = [p["id"] for p in kb.hydrate(_DIJKSTRA_SIGS, k=10).patterns]
        assert _alt_ids(res) == hydrate_order

    def test_improvement_annotated_only_when_strictly_faster(self):
        # detected O(n^2): every graph candidate (<= O(n log n)) is an improvement
        worse = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=_DIJKSTRA_SIGS)
        assert all("improvement" in a for a in worse["alternatives"])
        # detected O(1): nothing retrieved is faster -> no improvement annotation
        best = review_complexity(detected_complexity="O(1)", matched_signal_ids=_DIJKSTRA_SIGS)
        assert all("improvement" not in a for a in best["alternatives"])

    def test_detected_pattern_excluded_from_its_own_alternatives(self):
        res = review_complexity(detected_pattern="dijkstra", matched_signal_ids=_DIJKSTRA_SIGS)
        assert "dijkstra" not in _alt_ids(res)


# ==========================================================================
# Four-state fail-closed envelope — abstention keeps the retrieval-independent
# assessments (feasibility/structure/memory), never a husk
# ==========================================================================

class TestRetrievalStates:
    def test_hit_returns_ranked_alternatives(self):
        res = review_complexity(matched_signal_ids=_DIJKSTRA_SIGS)
        assert res["retrieval_state"] == HIT
        assert "dijkstra" in _alt_ids(res)

    def test_low_confidence_single_vote_still_surfaces(self):
        res = review_complexity(matched_signal_ids=_DIJKSTRA_SIGS[:1])
        assert res["retrieval_state"] == LOW_CONFIDENCE
        assert res["alternatives"]                             # surfaced, not empty

    def test_no_match_abstains_but_keeps_feasibility_and_structure(self):
        """NO_MATCH abstains to empty alternatives + populated envelope, but the
        retrieval-INDEPENDENT feasibility / structure_info still stand — not a husk."""
        res = review_complexity(detected_complexity="O(n^2)", detected_structures=["array"],
                                matched_signal_ids=["sig-does-not-exist"],
                                constraints={"n": 1_000_000})
        assert res["retrieval_state"] == NO_MATCH
        assert res["alternatives"] == [] and res["filtered_out"] == []   # no husk-alts
        assert res["unmatched"] == ["sig-does-not-exist"]
        assert res["feasibility"]["is_feasible"] is False and res["feasibility"]["reason"]
        assert "array" in res["structure_info"]               # retrieval-independent, kept

    def test_no_signals_abstains_no_match(self):
        res = review_complexity(detected_complexity="O(n)", constraints={"n": 1000})
        assert res["retrieval_state"] == NO_MATCH
        assert res["alternatives"] == []
        assert res["feasibility"]["is_feasible"] is True      # still assessed

    def test_dangling_abstains_but_keeps_feasibility(self):
        """DANGLING: every hydrated id fails to resolve (constructed fixture, per the
        engine's own dangling test — unreachable on the real corpus)."""
        loader = KnowledgeLoader()
        ghost = "sig-ghost0000000"
        loader._signal_index[ghost] = {
            "signal_id": ghost, "signal_text": "ghost", "pattern_ids": ["__absent__"],
        }
        with patch("mnemos.tools._shared.knowledge", loader):
            res = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=[ghost],
                                    constraints={"n": 1_000_000})
        assert res["retrieval_state"] == DANGLING
        assert res["alternatives"] == [] and res["filtered_out"] == []
        assert "__absent__" in res["dangling"]
        assert res["feasibility"]["is_feasible"] is False     # retrieval-independent, kept


# ==========================================================================
# structure_info — KEPT (operation costs for the detected structures)
# ==========================================================================

class TestStructureInfoKept:
    def test_detected_structures_return_operation_costs(self):
        res = review_complexity(detected_structures=["array", "hashmap"],
                                matched_signal_ids=_DIJKSTRA_SIGS)
        assert "array" in res["structure_info"] and "hashmap" in res["structure_info"]
        assert "operations" in res["structure_info"]["array"]


# ==========================================================================
# Empirical memory — KEPT (check_regression on the detected pattern, unchanged)
# ==========================================================================

class TestEmpiricalMemoryKept:
    def test_regression_on_detected_pattern_surfaces(self, _patch_memory, kb: KnowledgeLoader):
        store: MemoryStore = _patch_memory
        ds = kb.get_pattern("dijkstra").get("structure_id", "")
        store.add_regression(Regression(
            pattern="dijkstra", ds=ds, description="regressed on dense graphs",
            severity=Severity.high, project_id="default",
        ))
        res = review_complexity(detected_pattern="dijkstra", detected_complexity="O(n log n)",
                                matched_signal_ids=_DIJKSTRA_SIGS)
        regs = res["memory"].get("regressions", [])
        assert any(r["pattern"] == "dijkstra" for r in regs)

    def test_memory_annotation_never_reorders_alternatives(self, _patch_memory, kb: KnowledgeLoader):
        store: MemoryStore = _patch_memory
        before = _alt_ids(review_complexity(matched_signal_ids=_DIJKSTRA_SIGS))
        ds = kb.get_pattern("bellman-ford").get("structure_id", "")
        store.add_regression(Regression(
            pattern="bellman-ford", ds=ds, description="x", severity=Severity.high,
            project_id="default",
        ))
        after = _alt_ids(review_complexity(matched_signal_ids=_DIJKSTRA_SIGS))
        assert after == before

    def test_project_context_surfaces(self, _patch_memory):
        store: MemoryStore = _patch_memory
        store.set_context(CodebaseContext(
            project_id="proj-x", project_path="/tmp/x", language="python",
            structures_found=[StructureFound(type="hashmap", location="m.py", usage="cache")],
            runtime_constraints="max memory 256MB",
        ))
        res = review_complexity(matched_signal_ids=_DIJKSTRA_SIGS, project_id="proj-x")
        assert res["context"]["project_id"] == "proj-x"
        assert res["context"]["runtime_constraints"] == "max memory 256MB"


# ==========================================================================
# Determinism — identical input -> identical output (fresh loader + hashseed)
# ==========================================================================

class TestDeterminism:
    def test_identical_input_identical_output(self):
        a = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=_DIJKSTRA_SIGS,
                              constraints={"n": 1_000_000})
        b = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=_DIJKSTRA_SIGS,
                              constraints={"n": 1_000_000})
        assert _alt_ids(a) == _alt_ids(b)
        assert a["feasibility"] == b["feasibility"]
        assert [x["retrieval"] for x in a["alternatives"]] == \
               [x["retrieval"] for x in b["alternatives"]]

    def test_fresh_loader_matches_singleton(self):
        fresh = KnowledgeLoader()
        with patch("mnemos.tools._shared.knowledge", fresh):
            a = review_complexity(matched_signal_ids=_DIJKSTRA_SIGS)
        b = review_complexity(matched_signal_ids=_DIJKSTRA_SIGS)
        assert _alt_ids(a) == _alt_ids(b)

    def test_output_stable_across_pythonhashseed(self):
        """A PYTHONHASHSEED flip must not move the alternatives ranking or the votes."""
        import subprocess

        sigs = json.dumps(_DIJKSTRA_SIGS)
        snippet = (
            "import json;"
            "from mnemos.tools.review_complexity import review_complexity as f;"
            f"r=f(detected_complexity='O(n^2)', matched_signal_ids=json.loads('{sigs}'), k=10);"
            "print(json.dumps([(a['pattern_id'], a['retrieval']) for a in r['alternatives']]))"
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
        assert len(set(outs)) == 1, f"output moved across PYTHONHASHSEED: {outs}"


# ==========================================================================
# BAR-1 — the retrieval path reproduces the engine floor THROUGH review_complexity
# ==========================================================================

class TestBar1ThroughReviewComplexity:
    def test_alternatives_reproduce_engine_hydrate_order_per_problem(self, kb: KnowledgeLoader):
        """Reproduced, not re-derived: with no constraints and no detected pattern,
        review_complexity's alternatives are exactly the engine's hydrate order for
        every frozen problem (the tool just wraps the same hydrate call)."""
        for pid, sigs in MATCHES.items():
            engine = [p["id"] for p in kb.hydrate(sigs, k=10).patterns]
            tool = _alt_ids(review_complexity(matched_signal_ids=sigs, k=10))
            assert tool == engine, f"{pid}: review path diverged from engine hydrate order"
