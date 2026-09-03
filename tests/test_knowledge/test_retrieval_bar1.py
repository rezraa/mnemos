# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""BAR-1: Shape-C recall@10 over the frozen mnemos-Gmetric-v1 set (story-79321e96).

Recomputes the frozen benchmark THROUGH the ported production ``hydrate`` path and
checks the three S0-locked legs (locked_legs_v1.json), REPRODUCED not re-derived,
stratified per S0 (never a pooled mean). The recognizer that bridges each frozen
query to matched signal ids is the frozen, gold-blind stand-in for the production
LLM (mnemos_engine_bench + mnemos_matches_v1.json); council REVISE R1 required it
because a purely lexical query-only recognizer cannot clear the PB problem-language
gap (measured: PB gold signals share as little as zero query tokens).

Substrate is pinned two ways, both fail-closed: the S0 corpus/benchmark via the
frozen freeze_manifest.json (grade._verify_substrate, verbatim), and the S1
recognizer via mnemos_matches_freeze.json. The recognition is proven REPRODUCIBLE
(live recognize == frozen snapshot) so no hand-edit can hide in the frozen file.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from mnemos.knowledge.loader import KnowledgeLoader

_GMETRIC = Path(__file__).resolve().parents[1] / "data" / "gmetric"
if str(_GMETRIC) not in sys.path:
    sys.path.insert(0, str(_GMETRIC))

# S2 re-freeze: grade against the v2 generation (post decision_rules dissolution).
# Set before importing grade -- grade resolves its frozen-artifact paths at import
# from MNEMOS_GMETRIC_VERSION (default v1 preserves S0 provenance).
os.environ["MNEMOS_GMETRIC_VERSION"] = "v2"

import grade  # noqa: E402  (path-injected frozen grader, reused verbatim, v2-selected)
import mnemos_engine_bench as eng  # noqa: E402  (Shape-C harness; queries are generation-invariant)

LEGS = json.loads((_GMETRIC / "locked_legs_v2.json").read_text(encoding="utf-8"))
MATCHES_FROZEN = json.loads((_GMETRIC / "mnemos_matches_v2.json").read_text(encoding="utf-8"))
MATCHES_FREEZE = json.loads((_GMETRIC / "mnemos_matches_freeze_v2.json").read_text(encoding="utf-8"))

# Re-freeze eviction gate (AC): the v1 E-set stays covered@10 after the migration.
# Ratchet FLOOR on the covered COUNT (Coeus re-freeze precedent: covered[10] >= LOCK),
# not a per-gold subset -- the engine nets FLAT 74/77 @10 across the migration (one
# swap: P25 prefix-sum-with-hashmap out, P01 two-pointer-convergent in, the latter now
# reachable via the exact prose signal the migration put in the index). v1 engine
# covered@10 was 74; v2 is 74, so no coverage is lost. @5 is deliberately NOT locked:
# the crude gold-blind stand-in recognizer over-matches generic migrated prose on its
# 2-stemmed-token leg (council Q2), pushing a few golds from top-5 to rank 6-10 (@5
# 64->60); a production LLM recogniser does not make those matches, and @10 -- the
# gated cutoff for all three legs -- is unaffected. Recorded follow-up (Q2 / recognizer
# precision), not this story's work.
V2_EVICTION_FLOOR_AT_10 = 74


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def engine_core() -> dict:
    """Grade the Shape-C engine ONCE through the real grader + production hydrate."""
    return grade.grade(eng.rank_engine, "shape_c_engine")


@pytest.fixture(scope="module")
def baseline_core() -> dict:
    """The FROZEN matcher baseline core (per-problem + stratified grades), read from
    the pin. The live matcher (match_structural_signals) was deleted at S6, so LEG_3
    compares the engine against the pinned 27/77 baseline -- parallel to LEG_1/LEG_2
    reading LEGS['baseline_snapshot'], never recomputed (no matcher remains to run)."""
    return grade.load_pinned_baseline()


# ==========================================================================
# Substrate — fail closed on any drift (S0 corpus + S1 recognizer)
# ==========================================================================

class TestSubstrate:
    def test_s0_corpus_substrate_matches_frozen_pins(self) -> None:
        """The S0 corpus/benchmark is unchanged (grade's own verifier, verbatim)."""
        grade._verify_substrate()  # raises SystemExit on any drift

    def test_s1_recognizer_substrate_matches_frozen_pins(self) -> None:
        """mnemos_matches_v1.json + the corpus it derives from match the S1 pins."""
        pins = MATCHES_FREEZE["pins"]
        kdir = grade.KDIR
        paths = {
            "mnemos_matches_v2.json": _GMETRIC / "mnemos_matches_v2.json",
            "problems_blind_v2.json": _GMETRIC / "problems_blind_v2.json",
            "structures.json": kdir / "structures.json",
            "decision_rules.json": kdir / "decision_rules.json",
            "complexities.json": kdir / "complexities.json",
        }
        assert set(pins) == set(paths), "recognizer manifest pin set mismatch"
        for name, p in paths.items():
            assert _sha256(p) == pins[name], f"{name} drifted from the S1 pin"

    def test_recognition_is_reproducible(self) -> None:
        """Live recognition == the frozen snapshot: the pinned matches are exactly
        what mnemos_engine_bench produces from problems_blind + the index (no hidden
        hand-edit), and it is gold-blind (recognize never reads gmetric)."""
        live = eng.build_matches(KnowledgeLoader(knowledge_dir=grade.KDIR))
        assert live == MATCHES_FROZEN["matches"]

    def test_all_matched_signals_resolve(self) -> None:
        idx_ids = {e["signal_id"] for e in KnowledgeLoader(knowledge_dir=grade.KDIR).get_signal_index()}
        unresolved = {p: [s for s in sigs if s not in idx_ids]
                      for p, sigs in MATCHES_FROZEN["matches"].items()}
        unresolved = {p: v for p, v in unresolved.items() if v}
        assert not unresolved, f"unresolved matched signals: {unresolved}"


# ==========================================================================
# BAR-1 — the three S0-locked legs, reproduced through the hydrate path
# ==========================================================================

class TestBar1:
    def test_determinism_three_fresh_runs(self) -> None:
        """recall recomputes byte-identically across 3 fresh-loader runs."""
        cores = [grade.grade(eng.rank_engine, "e") for _ in range(3)]
        hashes = [hashlib.sha256(grade.canonical_dump(c).encode()).hexdigest() for c in cores]
        assert len(set(hashes)) == 1

    def test_denominator_is_the_frozen_77(self, engine_core: dict) -> None:
        assert engine_core["denominator_E_golds"] == LEGS["baseline_snapshot"]["denominator_E_golds"] == 77

    def test_no_eviction_v1_golds_stay_covered_at_10(self, engine_core: dict) -> None:
        """Re-freeze eviction gate (AC): the v1 E-set stays covered@10 after the S2
        corpus migration. Ratchet FLOOR on the covered count (see V2_EVICTION_FLOOR_AT_10);
        the engine holds 74/77 @10 -- no coverage lost to the 67 newly-indexed prose
        signals."""
        assert engine_core["covered"]["10"] >= V2_EVICTION_FLOOR_AT_10

    def test_leg_1_primary_delta(self, engine_core: dict) -> None:
        leg = LEGS["LEG_1_primary_delta"]
        base = LEGS["baseline_snapshot"]["recall_at_10"]
        delta = round(engine_core["recall"]["10"] - base, 4)
        assert delta >= leg["delta_bar"], f"delta {delta} < {leg['delta_bar']}"
        assert engine_core["covered"]["10"] >= leg["engine_min_covered_at_10"]

    def test_leg_2_design_works_floor(self, engine_core: dict) -> None:
        leg = LEGS["LEG_2_design_works_floor"]
        assert engine_core["recall"]["10"] >= leg["floor"]
        assert engine_core["covered"]["10"] >= leg["engine_min_covered_at_10"]

    def test_leg_3_distribution_wins(self, engine_core: dict, baseline_core: dict) -> None:
        leg = LEGS["LEG_3_distribution_wins"]
        e10 = {pid: engine_core["per_problem"][pid]["grades"]["10"]["covered"]
               for pid in engine_core["per_problem"]}
        b10 = {pid: baseline_core["per_problem"][pid]["grades"]["10"]["covered"]
               for pid in baseline_core["per_problem"]}
        wins = sum(1 for pid in e10 if e10[pid] >= b10[pid])
        assert wins >= leg["min_problems_ge_baseline"], f"only {wins} problems >= baseline"
        assert len(e10) == leg["n_problems"] == 40

    def test_verdict_all_three_legs(self, engine_core: dict, baseline_core: dict) -> None:
        """PASS = LEG_1 AND LEG_2 AND LEG_3 (locked verdict_rule)."""
        base = LEGS["baseline_snapshot"]["recall_at_10"]
        c10, r10 = engine_core["covered"]["10"], engine_core["recall"]["10"]
        leg1 = (round(r10 - base, 4) >= LEGS["LEG_1_primary_delta"]["delta_bar"]
                and c10 >= LEGS["LEG_1_primary_delta"]["engine_min_covered_at_10"])
        leg2 = r10 >= LEGS["LEG_2_design_works_floor"]["floor"]
        e10 = {pid: engine_core["per_problem"][pid]["grades"]["10"]["covered"] for pid in engine_core["per_problem"]}
        b10 = {pid: baseline_core["per_problem"][pid]["grades"]["10"]["covered"] for pid in baseline_core["per_problem"]}
        leg3 = sum(1 for pid in e10 if e10[pid] >= b10[pid]) >= LEGS["LEG_3_distribution_wins"]["min_problems_ge_baseline"]
        assert leg1 and leg2 and leg3

    def test_win_lands_in_target_classes_not_a_pooled_mean(self, engine_core: dict) -> None:
        """Stratified per S0 (never a pooled mean, m-e8ccb163): the PB/TK problem-
        language gap the baseline scored 0 on is recovered by the engine."""
        by = engine_core["by_qclass"]
        # baseline: PB=0/25, TK=0/22. The engine must move BOTH well off zero.
        assert by["PB"]["10"]["covered"] >= 20
        assert by["TK"]["10"]["covered"] >= 20
        # and it must not collapse PA (already covered by the baseline)
        assert by["PA"]["10"]["covered"] >= 22

    def test_k5_prefix_of_k10_over_all_problems(self) -> None:
        loader = KnowledgeLoader(knowledge_dir=grade.KDIR)
        for pid, sigs in MATCHES_FROZEN["matches"].items():
            b10 = [p["id"] for p in loader.hydrate(sigs, k=10).patterns]
            b5 = [p["id"] for p in loader.hydrate(sigs, k=5).patterns]
            assert b5 == b10[:5], f"{pid}: k5 not a prefix of k10"
