# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for the retrofitted suggest_refactor tool (story-1ec41914, council f1b39fbd S5).

suggest_refactor now rides the Shape-C engine as its SEED-FROM-NODE member: it already
HOLDS a known pattern id, so it seeds retrieval from THAT pattern's OWN structural
signals (``kb.signal_ids_for`` -> ONE ``kb.hydrate``), whose one-hop fan-out expands
over the pattern's ``alternatives`` edge -> complexity-feasibility + target GATE
(``filter_by_constraints``) -> the SHARED alternatives-fan-out (``_alternatives_fan_out``,
``only_better=True``) reasoned over each candidate's OWN fields. The old exact-id
``get_alternatives`` + ``get_structure`` scan with its flat 1.0/0.7 tuned ``score`` is gone.

Coverage:
  * the NEW output contract (suggestions with own-field fit + integer votes +
    improvement; retrieval_state/unmatched/dangling/filtered_out present; NO score);
  * SEED-FROM-NODE PROVEN — no matched_signal_ids param; the seed IS
    signal_ids_for(current_pattern); the candidate set IS the pattern's own
    alternatives (fan-out edge), invariant to current_complexity/target;
  * BAR-2 — the pinned pre-edit output (flat score, no envelope) vs the after
    (fit/retrieval/improvement + envelope), before/after delta asserted;
  * the four-state fail-closed envelope (HIT; constructed LOW_CONFIDENCE/DANGLING;
    NO_MATCH for an unknown/absent seed) — abstention keeps context/memory, never a husk;
  * the complexity-feasibility + target gate (candidate exceeding the target excluded
    into filtered_out; faster-first re-rank under a size constraint) and the "only if
    actually better" rank (non-faster candidates dropped, not merely un-annotated);
  * NO tuned scalar (no float anywhere; retrieval votes are ints);
  * empirical memory KEPT (get_corrections -> past_corrections; check_regression on
    suggestions -> regressions_on_suggestions; never re-orders); context KEPT;
  * determinism (identical input -> identical output; fresh loader; PYTHONHASHSEED).
"""

from __future__ import annotations

import inspect
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
    Correction,
    Regression,
    Severity,
)
from mnemos.tools.suggest_refactor import suggest_refactor

_GMETRIC = Path(__file__).resolve().parents[1] / "data" / "gmetric"
BAR2_PIN = json.loads((_GMETRIC / "suggest_refactor_bar2_pin.json").read_text(encoding="utf-8"))

# dijkstra is the canonical seed: O((V+E) log V) (~O(n log n)) with five resolvable,
# strictly-faster alternatives (bellman-ford + the bfs family) — a real corpus node.
_SEED = "dijkstra"
_SEED_CURRENT = "O(n log n)"
_SEED_ALTS = {"bellman-ford", "bfs-traversal", "zero-one-bfs", "bfs-shortest-unweighted", "spfa"}


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
    return [s["pattern_id"] for s in result["suggestions"]]


# ==========================================================================
# Output contract — husk gone; new keys present; own-field fit; integer votes
# ==========================================================================

class TestOutputContract:
    def test_new_contract_keys_present(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                               target_complexity="O(n)")
        for key in ("current", "suggestions", "filtered_out", "retrieval_state",
                    "unmatched", "dangling", "context", "memory", "constraints_analyzed"):
            assert key in res, f"missing contract key {key}"

    def test_suggestion_carries_own_fields_and_integer_votes(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        assert res["retrieval_state"] == HIT
        top = res["suggestions"][0]
        assert top["rank"] == 1
        assert set(top["fit"]) == {"complexity", "applies_when", "avoid_when", "constraints"}
        r = top["retrieval"]
        assert isinstance(r["score"], int) and isinstance(r["direct_votes"], int)
        assert all(not isinstance(v, float) for v in r.values())

    def test_retired_husk_surfaces_gone(self):
        """The tuned-scalar husk fields (score / when_better / ds / warnings) are gone."""
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        for s in res["suggestions"]:
            for dead in ("score", "when_better", "ds", "warnings", "demoted"):
                assert dead not in s, f"retired husk field {dead} still present"

    def test_current_echo_kept(self):
        res = suggest_refactor(current_pattern=_SEED, current_structure="heap",
                               current_complexity=_SEED_CURRENT, target_complexity="O(n)")
        assert res["current"] == {"pattern": _SEED, "structure": "heap",
                                  "complexity": _SEED_CURRENT, "target": "O(n)"}


# ==========================================================================
# SEED-FROM-NODE — proven: the seed IS the pattern's own signals, and the
# candidate set IS the pattern's alternatives (the fan-out edge)
# ==========================================================================

class TestSeedFromNode:
    def test_no_matched_signal_ids_param(self):
        """The seed-from-node distinction: unlike its siblings, suggest_refactor takes
        NO caller-supplied signal ids — retrieval is seeded from the node itself."""
        params = set(inspect.signature(suggest_refactor).parameters)
        assert "matched_signal_ids" not in params
        assert "current_pattern" in params

    def test_seed_is_the_patterns_own_signal_ids(self, kb: KnowledgeLoader):
        """The candidate set (suggestions + filtered_out + the excluded seed) is exactly
        the hydrate of the current pattern's OWN signal ids — not a caller recognition."""
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        seed_sigs = kb.signal_ids_for(_SEED)
        neighborhood = {p["id"] for p in kb.hydrate(seed_sigs, k=10).patterns}
        got = set(_ids(res)) | {f["pattern_id"] for f in res["filtered_out"]} | {_SEED}
        assert got == neighborhood
        assert res["unmatched"] == []       # the node's own signals all resolve

    def test_candidates_are_the_patterns_alternatives(self, kb: KnowledgeLoader):
        """Fans out over the pattern's ``alternatives`` edge: the candidate set for
        dijkstra is exactly its recorded alternatives (its whole neighborhood here)."""
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        candidates = set(_ids(res)) | {f["pattern_id"] for f in res["filtered_out"]}
        assert candidates == set(kb.get_pattern(_SEED)["alternatives"]) == _SEED_ALTS

    def test_retrieval_invariant_to_complexity_and_target(self):
        """Retrieval is seeded from the NODE, not the complexity/target: with a current
        complexity worse than every candidate and a target that excludes none, the FULL
        neighborhood surfaces regardless of the complexity/target pair — the seed node
        alone drives which candidates are retrieved."""
        a = suggest_refactor(current_pattern=_SEED, current_complexity="O(n^3)")
        b = suggest_refactor(current_pattern=_SEED, current_complexity="O(n^2)",
                             target_complexity="O(n^2)")
        assert set(_ids(a)) == set(_ids(b)) == _SEED_ALTS

    def test_seed_excluded_from_its_own_suggestions(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        assert _SEED not in _ids(res)
        assert _SEED not in {f["pattern_id"] for f in res["filtered_out"]}

    def test_rides_the_same_engine_as_hydrate(self, kb: KnowledgeLoader):
        """The seed path reproduces the engine (BAR-1 floor rides here too): with no
        gate, the candidate order is the engine's hydrate order minus the seed."""
        res = suggest_refactor(current_pattern=_SEED, current_complexity="O(n^3)")
        engine = [p["id"] for p in kb.hydrate(kb.signal_ids_for(_SEED), k=10).patterns
                  if p["id"] != _SEED]
        assert _ids(res) == engine


# ==========================================================================
# BAR-2 — the before/after that justifies the retrofit
# ==========================================================================

class TestBar2:
    def test_bar2_pin_captured_the_tuned_scalar_husk(self):
        """BAR-2 BEFORE (pinned pre-edit output): a flat tuned ``score`` on every
        suggestion and NO retrieval envelope."""
        before = BAR2_PIN["before_tuned_scalar"]
        assert before["suggestions"], "pin should carry the pre-edit suggestions"
        assert all(s.get("score") in (1.0, 0.7) for s in before["suggestions"])
        assert "retrieval_state" not in before      # no envelope before

    def test_bar2_delta_score_gone_envelope_added(self):
        """BAR-2 delta asserted: BEFORE every suggestion had a float ``score`` and there
        was no envelope; AFTER no suggestion has a score and the envelope is present,
        over the SAME input as the pin's case."""
        before = BAR2_PIN["before_tuned_scalar"]
        after = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                                 target_complexity="O(n)")
        assert all("score" in s for s in before["suggestions"])           # before: tuned scalar
        assert all("score" not in s for s in after["suggestions"])        # after: no scalar
        assert "retrieval_state" not in before and "retrieval_state" in after
        # both surface the same improving alternatives (the retrofit kept the answer)
        assert {s["pattern_id"] for s in after["suggestions"]} == \
               {s["pattern_id"] for s in before["suggestions"]}
        assert all("improvement" in s for s in after["suggestions"])


# ==========================================================================
# The gate + the "only if actually better" rank
# ==========================================================================

class TestGateAndRank:
    def test_candidate_exceeding_target_excluded_into_filtered_out(self):
        """A candidate whose OWN complexity exceeds the target is EXCLUDED from
        suggestions and surfaced in filtered_out with a reason."""
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                               target_complexity="O(log n)")
        assert res["suggestions"] == []                       # nothing beats O(log n) here
        filt = {f["pattern_id"]: f["reason"] for f in res["filtered_out"]}
        assert filt and set(filt) <= _SEED_ALTS
        assert all("target" in r for r in filt.values())

    def test_only_if_actually_better_drops_non_faster(self):
        """The "only if actually better" rank: a current complexity nothing beats
        yields ZERO suggestions (candidates dropped, not merely un-annotated)."""
        res = suggest_refactor(current_pattern=_SEED, current_complexity="O(1)")
        assert res["suggestions"] == []
        assert res["retrieval_state"] == HIT                  # retrieval still succeeded

    def test_every_suggestion_is_strictly_better_and_annotated(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        cur = _rank(_SEED_CURRENT)
        for s in res["suggestions"]:
            assert _rank(s["fit"]["complexity"]["time"]) < cur
            assert s["improvement"].startswith(f"{_SEED_CURRENT} -> ")

    def test_faster_first_rerank_under_size_constraint(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity="O(n^3)",
                               constraints={"n": 1_000_000})
        ranks = [_rank(s["fit"]["complexity"].get("time", "")) for s in res["suggestions"]]
        assert ranks == sorted(ranks), f"suggestions not faster-first: {ranks}"

    def test_no_constraint_preserves_hydrate_vote_order(self, kb: KnowledgeLoader):
        res = suggest_refactor(current_pattern=_SEED, current_complexity="O(n^3)")
        order = [p["id"] for p in kb.hydrate(kb.signal_ids_for(_SEED), k=10).patterns
                 if p["id"] != _SEED]
        assert _ids(res) == order


# ==========================================================================
# Four-state fail-closed envelope
# ==========================================================================

class TestRetrievalStates:
    def test_hit_returns_ranked_suggestions(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        assert res["retrieval_state"] == HIT
        assert res["suggestions"]

    def test_unknown_seed_abstains_no_match(self):
        """An unknown current_pattern has no indexed signals -> no_match abstains to
        empty, envelope present, never a husk."""
        res = suggest_refactor(current_pattern="does-not-exist", current_complexity="O(n^2)")
        assert res["retrieval_state"] == NO_MATCH
        assert res["suggestions"] == [] and res["filtered_out"] == []
        assert res["unmatched"] == [] and res["dangling"] == []

    def test_no_current_pattern_abstains_no_match(self):
        """No seed node at all -> nothing to seed from -> no_match (honest empty)."""
        res = suggest_refactor(current_complexity="O(n^2)")
        assert res["retrieval_state"] == NO_MATCH
        assert res["suggestions"] == []

    def test_low_confidence_single_vote_still_surfaces(self):
        """LOW_CONFIDENCE is unreachable on the real corpus (every pattern carries >=2
        signals, so a seed always self-votes to HIT); constructed here to prove the
        state propagates and still surfaces the candidate (not abstained)."""
        loader = KnowledgeLoader()
        seed_pat = {"id": "__seed__", "name": "seed", "complexity": {"time": "O(n^2)"},
                    "structural_signals": ["lone-seed-signal"], "alternatives": [_SEED]}
        loader._pattern_index["__seed__"] = ("array", seed_pat)
        sid = _signal_id("lone-seed-signal")
        loader._signal_index[sid] = {"signal_id": sid, "signal_text": "lone-seed-signal",
                                     "pattern_ids": ["__seed__"]}
        with patch("mnemos.tools._shared.knowledge", loader):
            res = suggest_refactor(current_pattern="__seed__", current_complexity="O(n^2)")
        assert res["retrieval_state"] == LOW_CONFIDENCE
        assert _SEED in _ids(res)                             # surfaced, not abstained

    def test_dangling_abstains_but_keeps_context(self, _patch_memory):
        """DANGLING: the seed's signal maps only to an absent pattern id (constructed
        fixture, per the engine's own dangling test). Abstains to empty, envelope
        surfaces the dangling id, retrieval-independent context still stands."""
        store: MemoryStore = _patch_memory
        store.set_context(CodebaseContext(
            project_id="proj-x", project_path="/tmp/x", language="python",
            structures_found=[], runtime_constraints="max memory 256MB",
        ))
        loader = KnowledgeLoader()
        ghost = _signal_id("ghost-seed-signal")
        loader._signal_index[ghost] = {"signal_id": ghost, "signal_text": "ghost-seed-signal",
                                       "pattern_ids": ["__absent__"]}
        with patch("mnemos.tools._shared.knowledge", loader):
            res = suggest_refactor(current_pattern="__absent__", current_complexity="O(n^2)",
                                   project_id="proj-x")
        assert res["retrieval_state"] == DANGLING
        assert res["suggestions"] == [] and res["filtered_out"] == []
        assert "__absent__" in res["dangling"]
        assert res["context"]["runtime_constraints"] == "max memory 256MB"


# ==========================================================================
# NO tuned scalar — the whole output surface is free of floats
# ==========================================================================

class TestNoTunedScalar:
    def test_no_float_anywhere_in_output(self):
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                               target_complexity="O(n)", constraints={"n": 1_000_000})

        def has_float(obj) -> bool:
            if isinstance(obj, bool):
                return False
            if isinstance(obj, float):
                return True
            if isinstance(obj, dict):
                return any(has_float(v) for v in obj.values())
            if isinstance(obj, (list, tuple)):
                return any(has_float(v) for v in obj)
            return False

        assert not has_float(res), "a tuned float scalar leaked into the output"


# ==========================================================================
# Empirical memory — KEPT (get_corrections + check_regression on suggestions)
# ==========================================================================

class TestEmpiricalMemoryKept:
    def test_past_corrections_surface(self, _patch_memory):
        store: MemoryStore = _patch_memory
        store.add_correction(Correction(
            original_pattern="bubble-sort", corrected_pattern="quicksort",
            reason="n too large", project_id="proj-x",
        ))
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                               project_id="proj-x")
        past = res["memory"].get("past_corrections", [])
        assert any(c["to"] == "quicksort" for c in past)

    def test_regression_on_suggestion_surfaces(self, _patch_memory, kb: KnowledgeLoader):
        store: MemoryStore = _patch_memory
        ds = kb.get_pattern("bellman-ford").get("structure_id", "")
        store.add_regression(Regression(
            pattern="bellman-ford", ds=ds, description="regressed on dense graphs",
            severity=Severity.high, project_id="default",
        ))
        res = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                               project_id="proj-x")
        regs = res["memory"].get("regressions_on_suggestions", [])
        assert any(r["pattern"] == "bellman-ford" for r in regs)

    def test_memory_never_reorders_suggestions(self, _patch_memory, kb: KnowledgeLoader):
        before = _ids(suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT))
        store: MemoryStore = _patch_memory
        ds = kb.get_pattern("bfs-traversal").get("structure_id", "")
        store.add_regression(Regression(
            pattern="bfs-traversal", ds=ds, description="x", severity=Severity.high,
            project_id="default",
        ))
        after = _ids(suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT))
        assert after == before


# ==========================================================================
# Determinism — identical input -> identical output (fresh loader + hashseed)
# ==========================================================================

class TestDeterminism:
    def test_identical_input_identical_output(self):
        a = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                             target_complexity="O(n)", constraints={"n": 1_000_000})
        b = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT,
                             target_complexity="O(n)", constraints={"n": 1_000_000})
        assert _ids(a) == _ids(b)
        assert [s["retrieval"] for s in a["suggestions"]] == \
               [s["retrieval"] for s in b["suggestions"]]

    def test_fresh_loader_matches_singleton(self):
        fresh = KnowledgeLoader()
        with patch("mnemos.tools._shared.knowledge", fresh):
            a = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        b = suggest_refactor(current_pattern=_SEED, current_complexity=_SEED_CURRENT)
        assert _ids(a) == _ids(b)

    def test_output_stable_across_pythonhashseed(self):
        """A PYTHONHASHSEED flip must not move the suggestion ranking or the votes."""
        import subprocess

        snippet = (
            "import json;"
            "from mnemos.tools.suggest_refactor import suggest_refactor as f;"
            f"r=f(current_pattern='{_SEED}', current_complexity='{_SEED_CURRENT}', k=10);"
            "print(json.dumps([(s['pattern_id'], s['retrieval']) for s in r['suggestions']]))"
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
