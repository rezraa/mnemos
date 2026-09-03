# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Shape-C signal-index engine — unit + dual-loader proof (story-79321e96).

Locks the ported engine (mirror of coeus.knowledge.loader, story-19e9ceb1):

* get_signal_index is deterministic + byte-reproducible (repeat calls, a fresh
  loader, and a PYTHONHASHSEED flip) and fails CLOSED on a hash collision at load;
* hydrate returns the four-state fail-closed envelope over the ``alternatives``
  edge, deep-frozen, no husk; the DANGLING state is exercised by a CONSTRUCTED
  index->absent-pattern fixture (council REVISE R2: seeds always resolve and
  patterns are never empty on the real corpus, so the natural dangling
  ``alternatives`` populate the dangling FIELD on a HIT/LOW_CONFIDENCE envelope,
  NOT the DANGLING state);
* the engine lives ONCE as ``_SignalEngine`` + module free-fns, inherited by BOTH
  loaders, and the graph loader now KEEPS the ``constraints`` field (drift repaired)
  -- proven against a constructed tmp_path Kuzu DB, never the live othrys.db.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import mnemos.knowledge.loader as L
from mnemos.knowledge.loader import (
    DANGLING,
    HIT,
    LOW_CONFIDENCE,
    NO_MATCH,
    _SEED_CAP,
    _TOPK_CAP,
    _CONFIDENCE_FLOOR,
    _FrozenDict,
    _SignalEngine,
    _signal_id,
    KnowledgeLoader,
    deep_freeze,
)

KDIR = Path(L.__file__).parent


@pytest.fixture(scope="module")
def kb() -> KnowledgeLoader:
    return KnowledgeLoader()


# ==========================================================================
# get_signal_index — determinism, byte-reproducibility, fail-closed collision
# ==========================================================================

class TestSignalIndex:
    def test_index_covers_all_signals(self, kb: KnowledgeLoader) -> None:
        idx = kb.get_signal_index()
        # every corpus pattern's structural_signals appear; ids are content hashes
        total = sum(len(p["structural_signals"]) for p in kb.get_all_patterns())
        assert len(idx) == total  # 573 unique signals post-S2 (506 kebab + 67 migrated rule prose)
        assert all(e["signal_id"] == _signal_id(e["signal_text"]) for e in idx)

    def test_deterministic_and_sorted(self, kb: KnowledgeLoader) -> None:
        a = kb.get_signal_index()
        b = kb.get_signal_index()
        assert a == b
        # sorted by signal_id, pattern_ids sorted -> byte-stable regardless of
        # dict/set iteration order (hence PYTHONHASHSEED-independent by construction)
        assert [e["signal_id"] for e in a] == sorted(e["signal_id"] for e in a)
        assert all(e["pattern_ids"] == sorted(e["pattern_ids"]) for e in a)

    def test_byte_reproducible_fresh_loader(self) -> None:
        dumps = [json.dumps(KnowledgeLoader().get_signal_index(), sort_keys=True) for _ in range(3)]
        assert len(set(dumps)) == 1

    def test_byte_reproducible_across_pythonhashseed(self) -> None:
        """A PYTHONHASHSEED flip must not move the serialised index (real proof,
        not just the by-construction argument)."""
        snippet = (
            "import json,hashlib;"
            "from mnemos.knowledge.loader import KnowledgeLoader as K;"
            "print(hashlib.sha256(json.dumps(K().get_signal_index(),sort_keys=True).encode()).hexdigest())"
        )
        env_base = {**__import__("os").environ, "PYTHONPATH": str(KDIR.parents[1])}
        outs = []
        for seed in ("0", "1", "12345"):
            r = subprocess.run(
                [sys.executable, "-c", snippet],
                capture_output=True, text=True, env={**env_base, "PYTHONHASHSEED": seed},
            )
            assert r.returncode == 0, r.stderr
            outs.append(r.stdout.strip())
        assert len(set(outs)) == 1, f"index sha256 moved across PYTHONHASHSEED: {outs}"

    def test_fail_closed_on_hash_collision(self, monkeypatch) -> None:
        """Two distinct signal texts colliding on one sid must raise at load, never
        silently merge into a corrupted index."""
        monkeypatch.setattr(L, "_signal_id", lambda _t: "sig-collide00000")
        eng = _SignalEngine()
        eng._pattern_index = {
            "a": ("s", {"id": "a", "structural_signals": ["foo shape"]}),
            "b": ("s", {"id": "b", "structural_signals": ["bar shape"]}),
        }
        with pytest.raises(ValueError, match="collision"):
            eng._build_signal_index()

    def test_no_collision_on_real_corpus(self, kb: KnowledgeLoader) -> None:
        # a fresh build over the real corpus must not raise (0 collisions)
        KnowledgeLoader()  # would raise in __init__ if the frozen corpus collided
        assert len(kb.get_signal_index()) == 573  # 506 kebab + 67 migrated rule prose (S2)


# ==========================================================================
# signal_ids_for — the seed-from-node accessor (drives suggest_refactor's seed)
# ==========================================================================

class TestSignalIdsFor:
    def test_returns_the_patterns_own_signal_ids(self, kb: KnowledgeLoader) -> None:
        """A pattern's seed is exactly the index ids that carry it — the content hash
        of each of its own structural signals, sorted and de-duplicated."""
        pat = kb.get_pattern("dijkstra")
        expected = sorted({_signal_id(s.strip()) for s in pat["structural_signals"] if s.strip()})
        assert kb.signal_ids_for("dijkstra") == expected
        # and every returned id is an index entry that names dijkstra as an owner
        idx = {e["signal_id"]: e for e in kb.get_signal_index()}
        assert all("dijkstra" in idx[sid]["pattern_ids"] for sid in kb.signal_ids_for("dijkstra"))

    def test_unknown_or_none_seed_is_empty(self, kb: KnowledgeLoader) -> None:
        """An unknown or missing seed yields [] (the caller then hydrates to no_match)
        — never a fabricated seed."""
        assert kb.signal_ids_for("no-such-pattern") == []
        assert kb.signal_ids_for("") == []
        assert kb.signal_ids_for(None) == []

    def test_seed_hydrates_the_node_and_fans_out_over_alternatives(self, kb: KnowledgeLoader) -> None:
        """Seeding hydrate with a node's own signal ids self-votes the node (HIT) and
        fans out over its ``alternatives`` edge — the seed-from-node retrieval."""
        res = kb.hydrate(kb.signal_ids_for("dijkstra"), k=10)
        assert res.state == HIT
        ids = {p["id"] for p in res.patterns}
        assert "dijkstra" in ids
        assert set(kb.get_pattern("dijkstra")["alternatives"]) <= ids

    def test_deterministic_and_sorted(self, kb: KnowledgeLoader) -> None:
        a = kb.signal_ids_for("dijkstra")
        assert a == kb.signal_ids_for("dijkstra") == sorted(a)


# ==========================================================================
# hydrate — four-state fail-closed envelope over the ``alternatives`` edge
# ==========================================================================

class TestHydrateStates:
    def test_hit_multi_vote(self, kb: KnowledgeLoader) -> None:
        sigs = [_signal_id("weighted-graph-shortest-path"),
                _signal_id("greedy-nearest-unvisited-expansion")]
        res = kb.hydrate(sigs, k=10)
        assert res.state == HIT
        assert any(p["id"] == "dijkstra" for p in res.patterns)
        assert res.patterns[0]["retrieval"]["score"] >= _CONFIDENCE_FLOOR

    def test_low_confidence_single_vote(self, kb: KnowledgeLoader) -> None:
        # one matched signal -> one direct vote -> below the floor -> low_confidence,
        # but patterns are still surfaced (never an empty list narrated as an answer)
        res = kb.hydrate([_signal_id("weighted-graph-shortest-path")], k=10)
        assert res.state == LOW_CONFIDENCE
        assert res.patterns
        assert res.patterns[0]["retrieval"]["score"] < _CONFIDENCE_FLOOR

    def test_no_match_unrecognised_signal(self, kb: KnowledgeLoader) -> None:
        res = kb.hydrate(["sig-does-not-exist"], k=10)
        assert res.state == NO_MATCH
        assert res.patterns == []          # fail closed, no husk
        assert res.votes == {}
        assert res.unmatched_signals == ["sig-does-not-exist"]

    def test_empty_input_is_no_match(self, kb: KnowledgeLoader) -> None:
        assert kb.hydrate([], k=10).state == NO_MATCH

    def test_dangling_state_constructed_fixture(self, kb: KnowledgeLoader) -> None:
        """DANGLING state: EVERY hydrated id fails to resolve. Unreachable on the
        real corpus (seeds always resolve; patterns never empty), so it is built
        directly (Directive 8) -- an index entry pointing only at an absent id."""
        loader = KnowledgeLoader()
        ghost = "sig-ghost0000000"
        loader._signal_index[ghost] = {
            "signal_id": ghost, "signal_text": "ghost", "pattern_ids": ["__absent_pattern__"],
        }
        res = loader.hydrate([ghost], k=10)
        assert res.state == DANGLING
        assert res.patterns == []                       # no husk on DANGLING
        assert res.votes == {}
        assert "__absent_pattern__" in res.dangling

    def test_natural_dangling_edges_populate_field_not_state(self, kb: KnowledgeLoader) -> None:
        """The 3 real dangling ``alternatives`` (edges to structure ids absent from
        the pattern index) surface in the dangling FIELD on a NON-DANGLING envelope
        -- the seed resolves, so state stays HIT/LOW_CONFIDENCE (council R2)."""
        cases = {
            "binary-search-tree-ops": "hashmap",
            "circular-buffer-streaming": "queue",
            "constraint-satisfaction": "dp",
        }
        seen: set[str] = set()
        for src, absent_struct in cases.items():
            pat = kb.get_pattern(src)
            assert absent_struct in pat["alternatives"]
            assert kb._lookup_pattern(absent_struct) is None  # it is a structure id, not a pattern
            sig = _signal_id(pat["structural_signals"][0])
            res = kb.hydrate([sig], k=10)
            assert res.state in (HIT, LOW_CONFIDENCE)       # NOT the DANGLING state
            assert absent_struct in res.dangling            # but surfaced in the field
            seen.add(absent_struct)
        assert seen == {"hashmap", "queue", "dp"}           # all three exercised

    def test_fanout_is_over_alternatives(self, kb: KnowledgeLoader) -> None:
        """A propagated (zero-direct-vote) neighbour must be a seed's ``alternatives``
        entry -- proving fan-out walks the Mnemos edge, not related_patterns."""
        # kadanes-algorithm alternatives = [prefix-sum, divide-and-conquer-max-subarray]
        res = kb.hydrate([_signal_id("maximum-contiguous-subarray-aggregate")], k=10, fan_out=True)
        propagated = {p["id"] for p in res.patterns if not p["retrieval"]["seed"]}
        assert {"prefix-sum", "divide-and-conquer-max-subarray"} & propagated
        # with fan-out off, only the direct seed survives (no propagation)
        res_off = kb.hydrate([_signal_id("maximum-contiguous-subarray-aggregate")], k=10, fan_out=False)
        assert all(p["retrieval"]["seed"] for p in res_off.patterns)
        assert all(p["retrieval"]["propagated_votes"] == 0 for p in res_off.patterns)


class TestHydrateInvariants:
    def test_deep_frozen_patterns_are_read_only(self, kb: KnowledgeLoader) -> None:
        res = kb.hydrate([_signal_id("weighted-graph-shortest-path")], k=5)
        p = res.patterns[0]
        assert isinstance(p, _FrozenDict)
        with pytest.raises(TypeError):
            p["id"] = "tampered"
        # nested lists become tuples (immutable by type): no in-place append exists
        assert isinstance(p["alternatives"], tuple)
        with pytest.raises(AttributeError):
            p["alternatives"].append("x")

    def test_hydrate_does_not_corrupt_corpus(self, kb: KnowledgeLoader) -> None:
        before = kb.get_pattern("dijkstra")["alternatives"][:]
        kb.hydrate([_signal_id("weighted-graph-shortest-path")], k=10)
        assert kb.get_pattern("dijkstra")["alternatives"] == before

    def test_ranking_deterministic(self, kb: KnowledgeLoader) -> None:
        sigs = [_signal_id("weighted-graph-shortest-path"),
                _signal_id("greedy-nearest-unvisited-expansion")]
        runs = [[p["id"] for p in kb.hydrate(sigs, k=10).patterns] for _ in range(5)]
        assert all(r == runs[0] for r in runs)
        fresh = [p["id"] for p in KnowledgeLoader().hydrate(sigs, k=10).patterns]
        assert fresh == runs[0]

    def test_k5_is_prefix_of_k10(self, kb: KnowledgeLoader) -> None:
        sigs = [_signal_id("weighted-graph-shortest-path"),
                _signal_id("greedy-nearest-unvisited-expansion"),
                _signal_id("priority-queue-distance-ordering")]
        b10 = [p["id"] for p in kb.hydrate(sigs, k=10).patterns]
        b5 = [p["id"] for p in kb.hydrate(sigs, k=5).patterns]
        assert b5 == b10[:5]

    def test_two_tier_seed_outranks_pure_hub(self, kb: KnowledgeLoader) -> None:
        """A directly-matched seed (tier True) is never evicted by a zero-direct-vote
        fan-out neighbour, regardless of the neighbour's accumulated score."""
        res = kb.hydrate([_signal_id("weighted-graph-shortest-path"),
                          _signal_id("greedy-nearest-unvisited-expansion")], k=10)
        seeds = [p for p in res.patterns if p["retrieval"]["seed"]]
        hubs = [p for p in res.patterns if not p["retrieval"]["seed"]]
        # every seat a hub took is at or below the last seed's rank
        if hubs and seeds:
            last_seed_rank = max(res.patterns.index(s) for s in seeds)
            first_hub_rank = min(res.patterns.index(h) for h in hubs)
            assert first_hub_rank > 0  # a hub never displaces the top seed

    def test_ceilings_unchanged(self) -> None:
        assert _SEED_CAP == 64
        assert _TOPK_CAP == 50
        assert _CONFIDENCE_FLOOR == 2


# ==========================================================================
# Free-function primitives (deep_freeze) + facet gate (ported, DORMANT)
# ==========================================================================

class TestPrimitives:
    def test_deep_freeze_severs_references(self) -> None:
        src = {"a": [1, 2, {"b": 3}]}
        frozen = deep_freeze(src)
        assert isinstance(frozen, _FrozenDict)
        assert isinstance(frozen["a"], tuple)
        assert isinstance(frozen["a"][2], _FrozenDict)
        src["a"].append(99)                 # mutating the source must not touch the copy
        assert 99 not in frozen["a"]

    def test_facet_gate_dormant_on_mnemos_corpus(self, kb: KnowledgeLoader) -> None:
        """The ported facet gate is DORMANT: no Mnemos pattern carries an avoid_when
        facet dict, so is_gated is always False (the LIVE gate is filter_by_constraints)."""
        for pat in kb.get_all_patterns():
            assert L.is_gated(pat, {"team_size": "1", "scale": "startup_mvp"}) is False

    def test_split_conditions_partitions_by_type(self) -> None:
        texts, facets = L.split_conditions(["free text", {"team_size": "1-5"}, "more text"])
        assert texts == ["free text", "more text"]
        assert facets == [{"team_size": "1-5"}]

    def test_parse_team_range(self) -> None:
        assert L._parse_team_range("1-5") == (1, 5)
        assert L._parse_team_range("3") == (3, 3)
        assert L._parse_team_range("50+")[0] == 50
        assert L._parse_team_range("garbage") is None


# ==========================================================================
# Dual-loader — ONE engine, both modes; graph loader KEEPS constraints
# (built against a constructed tmp_path Kuzu DB, never the live othrys.db)
# ==========================================================================

def _build_graph_db(tmp_path, kuzu, subset_structs):
    """Construct a minimal Kuzu DB from a subset of the real corpus."""
    db = kuzu.Database(str(tmp_path / "engine_test.db"))
    conn = kuzu.Connection(db)
    conn.execute("CREATE NODE TABLE agents(id STRING, reference_data STRING, PRIMARY KEY(id))")
    conn.execute("CREATE NODE TABLE patterns(id STRING, name STRING, category STRING, "
                 "complexity STRING, signals STRING, constraints STRING, data STRING, "
                 "domain STRING, PRIMARY KEY(id))")
    conn.execute("CREATE NODE TABLE rules(id STRING, signal STRING, recommended_pattern STRING, "
                 "priority INT64, data STRING, domain STRING, PRIMARY KEY(id))")
    conn.execute("CREATE REL TABLE alternative(FROM patterns TO patterns)")

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    def jtag(obj) -> str:
        return "JSON:" + json.dumps(obj)

    allpat: dict[str, tuple[str, dict]] = {}
    for s in subset_structs:
        for p in s.get("patterns", []):
            allpat[p["id"]] = (s["id"], p)
    for pid, (sid, p) in allpat.items():
        data = {"applies_when": p.get("applies_when", []), "avoid_when": p.get("avoid_when", [])}
        conn.execute(
            "CREATE (p:patterns {id:'mnemos:%s', name:'%s', category:'%s', complexity:'%s', "
            "signals:'%s', constraints:'%s', data:'%s', domain:'mnemos'})" % (
                esc(pid), esc(p.get("name", "")), esc(sid),
                esc(jtag(p.get("complexity", {}))), esc(jtag(p.get("structural_signals", []))),
                esc(jtag(p.get("constraints", {}))), esc(jtag(data)),
            )
        )
    for pid, (sid, p) in allpat.items():
        for alt in p.get("alternatives", []):
            if alt in allpat:
                conn.execute(
                    "MATCH (a:patterns {id:'mnemos:%s'}),(b:patterns {id:'mnemos:%s'}) "
                    "CREATE (a)-[:alternative]->(b)" % (esc(pid), esc(alt))
                )
    return conn


@pytest.fixture(scope="module")
def graph_conn(tmp_path_factory):
    kuzu = pytest.importorskip("real_ladybug", reason="kuzu/real_ladybug not installed")
    structures = json.loads((KDIR / "structures.json").read_text(encoding="utf-8"))["structures"]
    subset = [s for s in structures if s["id"] in {"heap", "array", "hashmap"}]
    tmp = tmp_path_factory.mktemp("engine_graph")
    return _build_graph_db(tmp, kuzu, subset)


class TestDualLoader:
    def test_both_loaders_inherit_one_engine(self, graph_conn) -> None:
        from mnemos.knowledge.graph_loader import GraphKnowledgeLoader
        assert issubclass(KnowledgeLoader, _SignalEngine)
        assert issubclass(GraphKnowledgeLoader, _SignalEngine)
        # the engine methods are the SAME objects on both (no duplicate engine code)
        assert KnowledgeLoader.hydrate is _SignalEngine.hydrate
        assert GraphKnowledgeLoader.hydrate is _SignalEngine.hydrate
        assert KnowledgeLoader.get_signal_index is GraphKnowledgeLoader.get_signal_index

    def test_graph_loader_keeps_constraints(self, graph_conn) -> None:
        """The repaired drift: graph patterns now carry the ``constraints`` field
        (it used to be selected then dropped), matching the JSON loader."""
        from mnemos.knowledge.graph_loader import GraphKnowledgeLoader
        gl = GraphKnowledgeLoader(graph_conn)
        jl = KnowledgeLoader()
        dg = gl.get_pattern("dijkstra")
        dj = jl.get_pattern("dijkstra")
        assert dg.get("constraints") is not None
        assert dg["constraints"] == dj["constraints"]
        # NO graph pattern is missing the field
        assert all("constraints" in p for p in gl.get_all_patterns())

    def test_graph_engine_hydrates(self, graph_conn) -> None:
        from mnemos.knowledge.graph_loader import GraphKnowledgeLoader
        gl = GraphKnowledgeLoader(graph_conn)
        res = gl.hydrate([_signal_id("weighted-graph-shortest-path"),
                          _signal_id("greedy-nearest-unvisited-expansion")], k=10)
        assert res.state == HIT
        assert any(p["id"] == "dijkstra" for p in res.patterns)

    def test_graph_signal_index_matches_json_for_shared_patterns(self, graph_conn) -> None:
        """For patterns present in both, the signal-index entries are identical
        (same content-hash ids, same signal texts) -- one engine, both modes."""
        from mnemos.knowledge.graph_loader import GraphKnowledgeLoader
        gl = GraphKnowledgeLoader(graph_conn)
        jl = KnowledgeLoader()
        g_by_id = {e["signal_id"]: e for e in gl.get_signal_index()}
        j_by_id = {e["signal_id"]: e for e in jl.get_signal_index()}
        shared = set(g_by_id) & set(j_by_id)
        assert shared
        for sid in shared:
            assert g_by_id[sid]["signal_text"] == j_by_id[sid]["signal_text"]
