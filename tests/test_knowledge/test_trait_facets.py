# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Problem-trait facets (story-c2df6429): provenance, primitives, ranking, guards.

North star: when a caller states a problem's traits, Mnemos reorders algorithms that
complexity cannot separate, from facets normalised out of each pattern's OWN written
guidance, so the problem -- not pattern-id order -- decides the tie.

* Provenance drift: every corpus facet cites a verbatim line of the same pattern's
  use_when / avoid_when / constraints (``facet_citations.json``), one-to-one, and every
  pattern is listed as reviewed.
* Primitives: ``facet_matches`` dispatches on the catalogue kind and honours ``any``.
* Ranking: avoid_when facets SINK (kept, flagged ``gated``), use_when facets break
  vote ties (``use_when_fit``); reorder only, fail-open, byte-reproducible; the three
  tools agree.
* Guards: no traits -> nothing moves; the frozen gmetric v2 traits -> no problem's
  best gold moves down and no gold leaves the top 10.
* Production path: a tmp_path seed in production order (Othrys ``import_titan`` then
  ``resolve_fleet_edges``) carries every facet into graph mode, where the facet layer
  decides exactly as in JSON mode.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import mnemos.knowledge.facet_catalogue_mirror as fc
from mnemos.knowledge.loader import (
    FACET_CATALOGUE,
    KnowledgeLoader,
    facet_matches,
    is_gated,
    split_conditions,
    use_when_fit,
)
from mnemos.memory.store import MemoryStore
from mnemos.tools.plan_algorithm import plan_algorithm
from mnemos.tools.review_complexity import review_complexity
from mnemos.tools.suggest_refactor import suggest_refactor

_KNOWLEDGE = Path(fc.__file__).resolve().parent
_CITATIONS = json.loads((_KNOWLEDGE / "facet_citations.json").read_text(encoding="utf-8"))
_GMETRIC = Path(__file__).resolve().parents[1] / "data" / "gmetric"
_REPOS = Path(__file__).resolve().parents[3]          # <repos>/mnemos/tests/.. -> <repos>


@pytest.fixture(scope="module")
def kb() -> KnowledgeLoader:
    return KnowledgeLoader()


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path):
    with patch("mnemos.tools._shared.memory", MemoryStore(memory_dir=tmp_path)):
        yield


def _sigs(kb: KnowledgeLoader, pid: str, count: int) -> list[str]:
    """*count* signal ids that route to *pid* alone (one direct vote each)."""
    own = sorted(e["signal_id"] for e in kb.get_signal_index() if e["pattern_ids"] == [pid])
    assert len(own) >= count, pid
    return own[:count]


def _sig(kb: KnowledgeLoader, pid: str) -> str:
    return _sigs(kb, pid, 1)[0]


def _view(result: dict, key: str = "recommendations") -> list[tuple[str, bool, int]]:
    return [(r["pattern_id"], r["gated"], r["retrieval"]["use_when_fit"]) for r in result[key]]


# ── Provenance drift ─────────────────────────────────────────────────────────
def _citation_violations(patterns: list[dict], citations: dict) -> list[str]:
    """Where the corpus facets and their citations disagree."""
    by_id = {p["id"]: p for p in patterns}
    bad: list[str] = []
    if sorted(citations["patterns_reviewed"]) != sorted(by_id):
        bad.append("reviewed-list != corpus patterns")
    cited = []
    for c in citations["facets"]:
        pat = by_id.get(c["pattern"])
        if pat is None:
            bad.append(f"unknown pattern {c['pattern']}")
            continue
        source = c["cites"]["field"]
        lines = [pat["constraints"]] if source == "constraints" else split_conditions(pat.get(source))[0]
        if source not in ("use_when", "avoid_when", "constraints") or c["cites"]["line"] not in lines:
            bad.append(f"uncited {c['pattern']}.{c['field']} {c['facet']}")
        cited.append((c["pattern"], c["field"], json.dumps(c["facet"], sort_keys=True)))
    corpus = [(p["id"], f, json.dumps(facet, sort_keys=True))
              for p in patterns for f in fc.FACET_FIELDS for facet in split_conditions(p.get(f))[1]]
    if sorted(cited) != sorted(corpus):
        bad.append(f"citations {len(cited)} != corpus facets {len(corpus)}")
    return bad


def test_every_corpus_facet_cites_a_line_of_its_own_pattern(kb):
    assert _citation_violations(kb.get_all_patterns(), _CITATIONS) == []
    assert len(_CITATIONS["facets"]) == 144
    assert len(_CITATIONS["patterns_reviewed"]) == 179


def _mutated(mutate) -> dict:
    cit = json.loads(json.dumps(_CITATIONS))
    mutate(cit)
    return cit


@pytest.mark.parametrize("label,mutate", [
    ("drop a citation", lambda c: c["facets"].pop()),
    ("cite another pattern's line", lambda c: c["facets"][0]["cites"].update(
        line=c["facets"][-1]["cites"]["line"])),
    ("paraphrase the cited line", lambda c: c["facets"][0]["cites"].update(
        line=c["facets"][0]["cites"]["line"] + " (paraphrased)")),
    ("cite a field that is not guidance", lambda c: c["facets"][0]["cites"].update(field="name")),
    ("forget a reviewed pattern", lambda c: c["patterns_reviewed"].pop()),
])
def test_citation_drift_mutants_are_red(kb, label, mutate):
    assert _citation_violations(kb.get_all_patterns(), _mutated(mutate)) != []


def test_an_uncited_corpus_facet_is_red(kb):
    patterns = json.loads(json.dumps(kb.get_all_patterns()))
    patterns[0]["use_when"].append({"input_order": "sorted"})
    assert _citation_violations(patterns, _CITATIONS) != []


# ── Primitives: kind dispatch + wildcard, fail open ──────────────────────────
@pytest.mark.parametrize("facet,traits,held", [
    ({"input_order": "sorted"}, {"input_order": "sorted"}, True),
    ({"input_order": "sorted"}, {"input_order": "unsorted"}, False),
    ({"input_order": "sorted"}, {}, False),                          # unstated: never credited
    ({"input_order": "any"}, {"input_order": "unsorted"}, True),     # declared wildcard
    ({"input_order": "any"}, {}, False),                             # wildcard needs the key stated
    ({"input_order": "sorted", "updates": "static"}, {"input_order": "sorted"}, False),  # AND
    ({"n": "1-1000"}, {"n": 500}, True),                             # int_range: overlap
    ({"n": "1-1000"}, {"n": 5000}, False),
    ({"n": "1-1000"}, {"n": "lots"}, False),                         # unparseable: fail open
])
def test_facet_matches_dispatches_on_the_catalogue_kind(facet, traits, held):
    assert facet_matches(facet, traits) is held


def test_gate_and_fit_read_the_patterns_own_facets(kb):
    dijkstra = kb.get_pattern("dijkstra")
    assert is_gated(dijkstra, {"value_sign": "may_be_negative"})
    assert not is_gated(dijkstra, {"value_sign": "non_negative"})
    assert use_when_fit(dijkstra, {"value_sign": "non_negative", "graph_weighting": "weighted"}) == 2
    assert use_when_fit(dijkstra, {}) == 0


# ── Ranking: the north-star ties, decided by the problem ─────────────────────
# (pattern that wins on id order, rival, traits under which the rival must win)
_TIES = [
    ("bellman-ford", "dijkstra", {"value_sign": "non_negative"}),
    ("fenwick-tree", "prefix-sum", {"updates": "static"}),
    ("hashset-membership", "sorted-array-binary-search",
     {"input_order": "sorted", "query_shape": "range_or_order"}),
]


@pytest.mark.parametrize("first,rival,traits", _TIES)
def test_traits_decide_a_tie_complexity_cannot_separate(kb, first, rival, traits):
    sigs = [_sig(kb, first), _sig(kb, rival)]
    plain = [r["pattern_id"] for r in plan_algorithm("p", sigs)["recommendations"]]
    assert plain[:2] == [first, rival]                                # id order decides today
    ranked = plan_algorithm("p", sigs, constraints=traits)["recommendations"]
    assert ranked[0]["pattern_id"] == rival
    assert first in [r["pattern_id"] for r in ranked]                 # sunk or out-fit, never dropped


@pytest.mark.parametrize("pid,traits", [
    ("dijkstra", {"value_sign": "may_be_negative"}),
    ("prefix-sum", {"updates": "dynamic"}),
    ("sorted-array-binary-search", {"updates": "dynamic"}),
])
def test_an_avoid_facet_sinks_below_every_ungated_candidate_and_is_kept(kb, pid, traits):
    rival = {"dijkstra": "bellman-ford", "prefix-sum": "fenwick-tree",
             "sorted-array-binary-search": "hashset-membership"}[pid]
    recs = plan_algorithm("p", [_sig(kb, pid), _sig(kb, rival)], constraints=traits)["recommendations"]
    flags = [r["gated"] for r in recs]
    assert flags == sorted(flags)                                     # every ungated above every gated
    gated = {r["pattern_id"] for r in recs if r["gated"]}
    assert pid in gated
    assert all(r["rank"] == i for i, r in enumerate(recs, start=1))


def test_fit_breaks_ties_only_within_equal_votes(kb):
    """A use_when facet never lifts a candidate over one with more direct votes."""
    sigs = _sigs(kb, "bellman-ford", 2) + [_sig(kb, "dijkstra")]
    recs = plan_algorithm("p", sigs, constraints={"value_sign": "non_negative"})["recommendations"]
    order = [r["pattern_id"] for r in recs]
    # bellman-ford has 2 direct votes but is gated (its avoid_when names non_negative):
    # it sinks; dijkstra (1 vote, fit 1) leads. Without the gate, votes would win:
    assert order[0] == "dijkstra" and recs[order.index("bellman-ford")]["gated"]
    plain = [r["pattern_id"] for r in plan_algorithm("p", sigs)["recommendations"]]
    assert plain[0] == "bellman-ford"
    lifted = plan_algorithm("p", sigs, constraints={"graph_weighting": "weighted"})["recommendations"]
    assert lifted[0]["pattern_id"] == "bellman-ford"                  # fit 1 for dijkstra cannot cross 2 votes


def test_three_tools_apply_the_same_gate(kb):
    traits = {"value_sign": "may_be_negative"}
    sigs = [_sig(kb, "dijkstra"), _sig(kb, "bellman-ford")]
    review = review_complexity(detected_complexity="O(n^2)", matched_signal_ids=sigs, constraints=traits)
    assert {a["pattern_id"]: a["gated"] for a in review["alternatives"]}["dijkstra"] is True
    refactor = suggest_refactor(current_pattern="floyd-warshall", current_complexity="O(V^3)",
                                constraints=traits)
    assert [(s["pattern_id"], s["gated"]) for s in refactor["suggestions"]] == \
           [("bellman-ford", False), ("dijkstra", True)]


def test_invalid_or_undeclared_trait_values_fail_open_and_are_surfaced(kb):
    sigs = [_sig(kb, "bellman-ford"), _sig(kb, "dijkstra")]
    plain = _view(plan_algorithm("p", sigs))
    bad = plan_algorithm("p", sigs, constraints={"value_sign": "positive", "sortedness": "SORTED"})
    assert _view(bad) == plain                                         # nothing applied
    assert "value_sign" in bad["invalid_constraint_values"]
    assert "sortedness" not in bad.get("unknown_constraints", {}).get("keys", [])  # a synonym


def test_caller_synonyms_and_case_resolve_to_the_declared_trait(kb):
    sigs = [_sig(kb, "hashset-membership"), _sig(kb, "sorted-array-binary-search")]
    canonical = _view(plan_algorithm("p", sigs, constraints={"input_order": "sorted"}))
    assert _view(plan_algorithm("p", sigs, constraints={"input_state": " Sorted "})) == canonical


def test_ranking_is_byte_reproducible(kb):
    sigs = [_sig(kb, "bellman-ford"), _sig(kb, "dijkstra"), _sig(kb, "prefix-sum")]
    traits = {"value_sign": "non_negative", "updates": "static"}
    runs = {json.dumps(plan_algorithm("p", sigs, constraints=traits), sort_keys=True) for _ in range(3)}
    assert len(runs) == 1


# ── Guards over the frozen gmetric v2 problems ───────────────────────────────
def _frozen():
    matches = json.loads((_GMETRIC / "mnemos_matches_v2.json").read_text(encoding="utf-8"))["matches"]
    gmetric = json.loads((_GMETRIC / "gmetric_v2.json").read_text(encoding="utf-8"))
    golds: dict[str, list[set[str]]] = {}
    for row in gmetric["reachable_set_map"]:
        if row["verdict"] == "E":
            golds.setdefault(row["problem"], []).append(set(row["acceptable_ids"]))
    traits = json.loads((_GMETRIC / "gmetric_traits_v2.json").read_text(encoding="utf-8"))["traits"]
    return matches, golds, traits


def test_no_traits_moves_nothing_on_any_frozen_problem():
    matches, _, _ = _frozen()
    for pid, sigs in matches.items():
        res = plan_algorithm("p", sigs)
        assert all(not r["gated"] and r["retrieval"]["use_when_fit"] == 0 for r in res["recommendations"]), pid


def _gold_ranks(ids: list[str], golds: list[set[str]]) -> list[int]:
    return [next((i for i, x in enumerate(ids) if x in g), 99) for g in golds]


def test_frozen_traits_move_no_problem_the_wrong_way():
    """Per problem: the best-ranked gold never moves down and no gold leaves the top
    10. Measured right-way (best gold to rank 1): P12, P15, P23."""
    matches, golds, traits = _frozen()
    right, wrong = [], []
    for pid, stated in sorted(traits.items()):
        base = [r["pattern_id"] for r in plan_algorithm("p", matches[pid])["recommendations"]]
        moved = [r["pattern_id"] for r in plan_algorithm("p", matches[pid], constraints=stated)["recommendations"]]
        before, after = _gold_ranks(base, golds.get(pid, [])), _gold_ranks(moved, golds.get(pid, []))
        if min(after, default=99) > min(before, default=99):
            wrong.append(pid)
        if min(after, default=99) < min(before, default=99):
            right.append(pid)
        assert sum(r < 10 for r in after) >= sum(r < 10 for r in before), pid
    assert wrong == []
    assert right == ["P12", "P15", "P23"]


# ── Production path: seeded in production order, graph mode decides the same ─
def _othrys_src() -> Path | None:
    src = _REPOS / "othrys" / "src"
    return src if (src / "othrys" / "importers" / "__init__.py").exists() else None


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """A tmp_path DB seeded exactly as setup does: PASS 1 ``import_titan`` from this
    repo, then PASS 2 ``resolve_fleet_edges``. Never the live othrys.db."""
    src = _othrys_src()
    if src is None:
        pytest.skip("othrys sibling repo absent (test-only dependency)")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    kuzu = pytest.importorskip("real_ladybug")
    from othrys.importers import import_titan, resolve_fleet_edges
    from othrys.schema import init_db

    from mnemos.knowledge.graph_loader import GraphKnowledgeLoader

    tmp = tmp_path_factory.mktemp("seed")
    conn = kuzu.Connection(init_db(tmp / "seed.db"))
    import_titan(_REPOS / "mnemos", "mnemos", conn)
    package = tmp / "packages" / "mnemos" / "repo" / "src" / "mnemos" / "knowledge"
    package.mkdir(parents=True)
    for f in _KNOWLEDGE.glob("*.json"):                    # this repo's corpus + manifest
        shutil.copy2(f, package / f.name)
    resolve_fleet_edges(conn, packages_root=tmp / "packages", spool_path=str(tmp / "spool.jsonl"))
    return conn, GraphKnowledgeLoader(conn)


def test_every_facet_survives_the_seed(seeded, kb):
    _, graph = seeded
    json_mode = {p["id"]: p for p in kb.get_all_patterns()}
    graph_mode = {p["id"]: p for p in graph.get_all_patterns()}
    assert json_mode.keys() == graph_mode.keys()
    for pid, pat in json_mode.items():
        for field in fc.FACET_FIELDS:
            assert list(graph_mode[pid][field]) == list(pat[field]), (pid, field)


def test_graph_mode_facet_decisions_equal_json_mode(seeded, kb):
    """Every pattern x every declared trait value: identical gate and fit."""
    _, graph = seeded
    graph_mode = {p["id"]: p for p in graph.get_all_patterns()}
    for key, spec in FACET_CATALOGUE.specs.items():
        for value in spec.values if spec.kind == "enum" else ():
            traits = {key: value}
            for pat in kb.get_all_patterns():
                other = graph_mode[pat["id"]]
                assert (is_gated(pat, traits), use_when_fit(pat, traits)) == \
                       (is_gated(other, traits), use_when_fit(other, traits)), (pat["id"], traits)


def _facet_probes(kb) -> list[tuple[str, dict]]:
    return [(p["id"], dict(f)) for p in kb.get_all_patterns()
            for field in fc.FACET_FIELDS for f in split_conditions(p.get(field))[1]]


def test_graph_mode_tool_output_equals_json_mode_wherever_retrieval_agrees(seeded, kb):
    """For each facet probe (a pattern's own signals + the trait its facet names),
    the traits add no graph/JSON divergence: every probe whose trait-free output
    agrees across modes also agrees with the traits applied, and every probe that
    differs already differs without traits. Where both modes return a pattern, its
    gate flag is identical. With the alternative fan-out seeded one row per authored
    reference, every probe agrees."""
    conn, _ = seeded
    agree = 0
    for pid, traits in _facet_probes(kb):
        sigs = kb.signal_ids_for(pid)
        plain = _view(plan_algorithm("p", sigs)) == _view(plan_algorithm("p", sigs, conn=conn))
        j = plan_algorithm("p", sigs, constraints=traits)
        g = plan_algorithm("p", sigs, constraints=traits, conn=conn)
        assert (_view(j) == _view(g)) == plain, (pid, traits)
        agree += plain
        jf = {r["pattern_id"]: r["gated"] for r in j["recommendations"]}
        gf = {r["pattern_id"]: r["gated"] for r in g["recommendations"]}
        assert all(jf[x] == gf[x] for x in jf.keys() & gf.keys()), (pid, traits)
    assert agree == len(_facet_probes(kb)) == 144
