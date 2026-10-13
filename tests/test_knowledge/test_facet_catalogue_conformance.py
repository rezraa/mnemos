# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Mnemos facet catalogue — conformance, fail-closed fixtures, and mutants
(story-80d92a4b; problem-trait keys story-c2df6429).

The catalogue declares every caller-constraint key a reader acts on, so a key it
does not declare can be reported instead of silently doing nothing. Two readers:
``filter_by_constraints`` EXCLUDES on the complexity keys (n, space,
target_complexity), and the facet gate (``is_gated`` / ``use_when_fit``) reorders
on the problem-trait keys the corpus facets name. The binding test proves the
catalogue and the readers agree in behaviour: every declared spelling moves at
least one pattern through one reader, and a near-miss spelling moves nothing. The
complexity values are the gate's own ladder (``complexities.json`` input-size
guidelines), and every time-target description carries that guideline's own
wording. Every declared trait value is named by at least one corpus facet.

Corpus-facet validation at setup checks every facet (count asserted); the
fail-closed behaviour is proven on constructed fixtures. Shape parity with the
Othrys reader is the Othrys-side drift test's job (``tests/test_facet_catalogue.py``
there).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import mnemos.knowledge.facet_catalogue_mirror as fc
from mnemos.knowledge.loader import KnowledgeLoader, is_gated, split_conditions, use_when_fit
from mnemos.tools import _shared

_KNOWLEDGE = Path(fc.__file__).resolve().parent
_CATALOGUE_JSON = _KNOWLEDGE / fc.CATALOGUE_NAME


@pytest.fixture(scope="module")
def kb() -> KnowledgeLoader:
    return KnowledgeLoader()


def _raw() -> dict:
    return json.loads(_CATALOGUE_JSON.read_text(encoding="utf-8"))


def _guidelines() -> dict:
    return json.loads((_KNOWLEDGE / "complexities.json").read_text(encoding="utf-8"))["input_size_guidelines"]


# Spellings probed against the gate, each with a value that filters part of the
# corpus when the gate reads it: the four the gate reads plus two measured misses.
_GATE_PROBES = {"n": 10**9, "input_size": 10**9, "space": "O(1)", "target_complexity": "O(1)",
                "N": 10**9, "max_space": "O(1)"}
_KIND_PROBE = {"int_range": 10**9, "complexity_class": "O(1)", "enum": "x"}


def _moves_a_trait_facet(catalogue: fc.FacetCatalogue, patterns: list[dict], name: str) -> bool:
    """Does stating *name* with some declared value gate or lift a corpus pattern?"""
    spec = catalogue.specs[catalogue.names[name]]
    for value in spec.values or ():
        traits = fc.resolve_constraints(catalogue, {name: value}).values
        if any(is_gated(p, traits) or use_when_fit(p, traits) for p in patterns):
            return True
    return False


def _binding_violations(catalogue: fc.FacetCatalogue, kb: KnowledgeLoader) -> list[str]:
    """Where the catalogue and its readers disagree: a declared spelling no reader
    acts on, or a spelling the exclusion gate reads that is undeclared."""
    patterns = kb.get_all_patterns()
    probes = dict(_GATE_PROBES)
    for name, key in catalogue.names.items():
        probes.setdefault(name, _KIND_PROBE[catalogue.specs[key].kind])
    read = {name for name, value in probes.items()
            if kb.filter_by_constraints(patterns, {name: value})[1]}
    read |= {name for name, key in catalogue.names.items()
             if catalogue.specs[key].kind == "enum" and _moves_a_trait_facet(catalogue, patterns, name)}
    declared = set(catalogue.names)
    return (sorted(f"declared-but-ignored:{n}" for n in declared - read)
            + sorted(f"read-but-undeclared:{n}" for n in read - declared))


# ── The shipped catalogue ────────────────────────────────────────────────────
_TRAITS = {
    "updates": (("static", "dynamic"), ("update_pattern", "mutability")),
    "arrival": (("batch", "streaming"), ("data_arrival",)),
    "input_order": (("sorted", "unsorted"), ("input_state", "sortedness")),
    "query_shape": (("point", "range_or_order", "prefix"), ("query_type",)),
    "exactness": (("exact", "approximate"), ("accuracy",)),
    "value_sign": (("non_negative", "may_be_negative"), ("sign",)),
    "graph_direction": (("directed", "undirected"), ("edge_direction",)),
    "graph_weighting": (("unweighted", "zero_one", "weighted"), ("edge_weights", "weighting")),
}


def test_shipped_catalogue_declares_exactly_the_gate_and_trait_keys():
    cat = fc.load_catalogue()
    assert cat.domain == "mnemos"
    gate = {k: (s.kind, s.synonyms, s.wildcard) for k, s in cat.specs.items() if s.kind != "enum"}
    assert gate == {
        "n": ("int_range", ("input_size",), None),
        "space": ("complexity_class", (), None),
        "target_complexity": ("complexity_class", (), None),
    }
    traits = {k: (tuple(s.values), s.synonyms) for k, s in cat.specs.items() if s.kind == "enum"}
    assert traits == _TRAITS
    assert all(cat.specs[k].wildcard[0] == "any" for k in _TRAITS)
    # Algorithm PROPERTIES (time, space, stability, in-place) live in each pattern's
    # own complexity data, never as problem-trait facets.
    assert not {"time", "stability", "stable", "in_place"} & set(cat.names)


def test_every_declared_trait_value_is_named_by_a_corpus_facet(kb):
    cat = fc.load_catalogue()
    named = {(k, v) for p in kb.get_all_patterns() for field in fc.FACET_FIELDS
             for f in split_conditions(p.get(field))[1] for k, v in f.items()}
    declared = {(k, v) for k in _TRAITS for v in cat.specs[k].values}
    assert declared - named == set()


def test_catalogue_binds_filter_by_constraints(kb):
    assert _binding_violations(fc.load_catalogue(), kb) == []


def test_complexity_values_are_the_gates_ladder_and_described_from_it():
    """Both complexity keys offer exactly the tiers the gate ranks; each time-target
    description quotes its guideline's own wording (no invented claim)."""
    cat, guide = fc.load_catalogue(), _guidelines()
    for key in ("space", "target_complexity"):
        assert list(cat.specs[key].values) == list(guide)
    for tier, text in cat.specs["target_complexity"].values.items():
        assert guide[tier]["description"] in text


def test_every_key_and_value_is_described():
    cat = fc.load_catalogue()
    for spec in cat.specs.values():
        assert spec.description
        assert all((spec.values or {}).values())


def test_setup_validates_every_corpus_facet(kb):
    assert fc.validate_facets(fc.load_catalogue(), kb.get_all_patterns()) == 144


def test_tools_load_the_shipped_catalogue_at_import():
    assert _shared.FACET_CATALOGUE == fc.load_catalogue()


# ── Fail-closed fixtures (each RED) ──────────────────────────────────────────
_CAT = {"domain": "t", "facets": {
    "scale": {"kind": "enum", "description": "Scale of the system.",
              "values": {"growth": "Growing product.", "enterprise": "Large organisation."},
              "wildcard": {"value": "any", "description": "Any scale."}},
    "team_size": {"kind": "int_range", "description": "People on the team."},
    "space": {"kind": "complexity_class", "description": "Space budget.",
              "values": {"O(1)": "Constant.", "O(n)": "Linear."}, "synonyms": ["max_space"]},
}}


def _with(mutate) -> dict:
    cat = json.loads(json.dumps(_CAT))
    mutate(cat)
    return cat


def _pat(*facets):
    return [{"id": "p", "use_when": ["prose", *facets]}]


@pytest.mark.parametrize("facet,error", [
    ({"scael": "growth"}, fc.UnknownFacetKey),               # unknown key
    ({"max_space": "O(1)"}, fc.UnknownFacetKey),             # a synonym is caller-only
    ({"scale": "grwoth"}, fc.DisallowedFacetValue),          # disallowed value
    ({"team_size": "five"}, fc.DisallowedFacetValue),        # wrong kind (int_range)
    ({"team_size": "9-3"}, fc.DisallowedFacetValue),         # inverted range
    ({"team_size": "²"}, fc.DisallowedFacetValue),           # non-ASCII digit
    ({"space": "O(n^2)"}, fc.DisallowedFacetValue),          # undeclared complexity class
    ({"space": "linear"}, fc.DisallowedFacetValue),          # wrong kind (complexity_class)
    ({"scale": ["growth"]}, fc.DisallowedFacetValue),        # wrong type
    ({"scale": "g" * (fc.MAX_VALUE_CHARS + 1)}, fc.DisallowedFacetValue),  # oversize value
    ({}, fc.FacetCatalogueError),                            # empty facet never matches
])
def test_corpus_facet_fixture_is_red(facet, error):
    cat = fc.validate_catalogue(_CAT)
    with pytest.raises(error):
        fc.validate_facets(cat, _pat(facet))


def test_valid_facets_pass_including_wildcard_and_range_grammar():
    cat = fc.validate_catalogue(_CAT)
    facets = [{"scale": "any"}, {"scale": "growth", "team_size": "1-5"}, {"team_size": "50+"},
              {"team_size": 3}, {"space": "O(n)"}]
    assert fc.validate_facets(cat, _pat(*facets)) == len(facets)


@pytest.mark.parametrize("label,catalogue", [
    ("unknown top field", _with(lambda c: c.update(facet={}))),
    ("unknown key field", _with(lambda c: c["facets"]["scale"].update(value={"x": "y"}))),
    ("wrong kind", _with(lambda c: c["facets"]["team_size"].update(kind="range"))),
    ("enum without values", _with(lambda c: c["facets"]["scale"].pop("values"))),
    ("complexity_class without values", _with(lambda c: c["facets"]["space"].pop("values"))),
    ("values on an int_range", _with(lambda c: c["facets"]["team_size"].update(values={"1": "one"}))),
    ("values as a list", _with(lambda c: c["facets"]["scale"].update(values=["growth"]))),
    ("empty enum", _with(lambda c: c["facets"]["scale"].update(values={}))),
    ("non-big-O class", _with(lambda c: c["facets"]["space"]["values"].update(linear="Linear."))),
    ("wildcard is a value", _with(lambda c: c["facets"]["scale"]["wildcard"].update(value="growth"))),
    ("wildcard as a bare token", _with(lambda c: c["facets"]["scale"].update(wildcard="any"))),
    ("values differ only in case", _with(lambda c: c["facets"]["scale"]["values"].update(Growth="x"))),
    ("padded value", _with(lambda c: c["facets"]["scale"]["values"].update({" growth ": "x"}))),
    ("synonym collides with a key", _with(lambda c: c["facets"]["space"].update(synonyms=["scale"]))),
    ("key missing description", _with(lambda c: c["facets"]["team_size"].pop("description"))),
    ("value missing description", _with(lambda c: c["facets"]["scale"]["values"].update(growth=""))),
    ("wildcard missing description", _with(lambda c: c["facets"]["scale"]["wildcard"].pop("description"))),
    ("description too long", _with(lambda c: c["facets"]["scale"].update(
        description="d" * (fc.MAX_DESCRIPTION_CHARS + 1)))),
    ("too many keys", _with(lambda c: c["facets"].update(
        {f"k{i}": {"kind": "int_range", "description": "k"} for i in range(fc.MAX_FACET_KEYS)}))),
    ("too many values", _with(lambda c: c["facets"]["scale"].update(
        values={f"v{i}": "v" for i in range(fc.MAX_VALUES_PER_KEY + 1)}))),
    ("too many synonyms", _with(lambda c: c["facets"]["space"].update(
        synonyms=[f"s{i}" for i in range(fc.MAX_SYNONYMS_PER_KEY + 1)]))),
    ("value too long", _with(lambda c: c["facets"]["scale"].update(
        values={"v" * (fc.MAX_VALUE_CHARS + 1): "v"}))),
    ("no domain", _with(lambda c: c.pop("domain"))),
])
def test_catalogue_fixture_is_red(label, catalogue):
    with pytest.raises(fc.FacetCatalogueError):
        fc.validate_catalogue(catalogue)


def test_oversize_file_is_red(tmp_path, monkeypatch):
    p = tmp_path / fc.CATALOGUE_NAME
    p.write_text(json.dumps(_CAT), encoding="utf-8")
    monkeypatch.setattr(fc, "_MAX_BYTES", 16)
    with pytest.raises(fc.FacetCatalogueError, match="byte ceiling"):
        fc.load_catalogue(p)


def test_too_deep_file_is_red(tmp_path):
    p = tmp_path / fc.CATALOGUE_NAME
    p.write_text('{"domain": "t", "facets": ' + "[" * 50 + "]" * 50 + "}", encoding="utf-8")
    with pytest.raises(fc.FacetCatalogueError, match="nests past"):
        fc.load_catalogue(p)


# ── Mutants: each breaks a guarantee, and the test that owns it goes red ────
def test_mutant_drop_synonym_breaks_the_binding(kb):
    raw = _raw()
    raw["facets"]["n"].pop("synonyms")
    assert _binding_violations(fc.validate_catalogue(raw), kb) == ["read-but-undeclared:input_size"]


def test_mutant_declare_an_unread_key_breaks_the_binding(kb):
    raw = _raw()
    raw["facets"]["online"] = {"kind": "enum", "description": "Data arrives over time.",
                               "values": {"yes": "Streaming.", "no": "Batch."}}
    assert _binding_violations(fc.validate_catalogue(raw), kb) == ["declared-but-ignored:online"]


def test_mutant_drop_wildcard_rejects_the_wildcard_value():
    no_wild = _with(lambda c: c["facets"]["scale"].pop("wildcard"))
    with pytest.raises(fc.DisallowedFacetValue):
        fc.validate_facets(fc.validate_catalogue(no_wild), _pat({"scale": "any"}))


def test_mutant_drop_a_description_from_the_shipped_catalogue_is_red():
    raw = _raw()
    raw["facets"]["space"]["values"]["O(1)"] = ""
    with pytest.raises(fc.FacetCatalogueError, match="O\\(1\\)"):
        fc.validate_catalogue(raw)


# ── Caller values resolved by kind (story-0ed4bd1f) ──────────────────────────
@pytest.mark.parametrize("constraints,values", [
    ({"scale": "growth"}, {"scale": "growth"}),
    ({"scale": "GROWTH"}, {"scale": "growth"}),                 # enum: case-insensitive
    ({"scale": " Enterprise "}, {"scale": "enterprise"}),       # surrounding space
    ({"scale": "ANY"}, {"scale": "any"}),                       # wildcard canonicalised
    ({"max_space": "o(n)"}, {"space": "O(n)"}),                 # synonym -> key
    ({"team_size": 5}, {"team_size": 5}),
    ({"team_size": "12"}, {"team_size": 12}),                   # digit string -> int
    ({"team_size": 12.0}, {"team_size": 12}),                   # whole float -> int
    ({"space": "O(1)", "max_space": "O(n)"}, {"space": "O(1)"}),  # the key beats a synonym
    ({"max_space": "O(n)", "space": "O(1)"}, {"space": "O(1)"}),  # ... in either order
    ({"scale": None}, {}),                                      # None is absent
    ({"scael": "growth"}, {}),                                  # undeclared: not a value error
])
def test_caller_values_resolve_to_the_canonical_declared_value(constraints, values):
    resolved = fc.resolve_constraints(fc.validate_catalogue(_CAT), constraints)
    assert dict(resolved.values) == values
    assert dict(resolved.invalid) == {}


@pytest.mark.parametrize("constraints,spelling,extra", [
    ({"scale": "grwoth"}, "scale", {"allowed": ["growth", "enterprise", "any"]}),
    ({"scale": 3}, "scale", {"allowed": ["growth", "enterprise", "any"]}),
    ({"max_space": "O(n^2)"}, "max_space", {"allowed": ["O(1)", "O(n)"]}),
    ({"team_size": "1-5"}, "team_size", {"example": 1000000}),
    ({"team_size": "²"}, "team_size", {"example": 1000000}),
    ({"team_size": "9" * (fc.MAX_VALUE_CHARS + 1)}, "team_size", {"example": 1000000}),
])
def test_caller_values_outside_the_catalogue_are_surfaced(constraints, spelling, extra):
    resolved = fc.resolve_constraints(fc.validate_catalogue(_CAT), constraints)
    assert dict(resolved.values) == {}
    report = dict(resolved.invalid[spelling])
    assert report.pop("reason")
    assert report.pop("value") is not None
    assert report == extra


def test_an_invalid_key_spelling_falls_back_to_a_valid_synonym():
    resolved = fc.resolve_constraints(fc.validate_catalogue(_CAT), {"space": "bad", "max_space": "o(1)"})
    assert dict(resolved.values) == {"space": "O(1)"}
    assert list(resolved.invalid) == ["space"]


def test_mutant_filter_reads_its_synonyms_from_the_catalogue(kb, monkeypatch):
    """The gate hard-codes no spelling: a synonym added to the catalogue is read."""
    import mnemos.knowledge.loader as loader_mod

    raw = _raw()
    raw["facets"]["n"]["synonyms"].append("size")
    patterns = kb.get_all_patterns()
    assert not kb.filter_by_constraints(patterns, {"size": 10**9})[1]
    monkeypatch.setattr(loader_mod, "FACET_CATALOGUE", fc.validate_catalogue(raw))
    assert kb.filter_by_constraints(patterns, {"size": 10**9})[1]
