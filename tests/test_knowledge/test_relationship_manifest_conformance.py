# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Mnemos relationship-manifest conformance — stdlib only, NO ``othrys`` import.

The per-repo half of the manifest contract: the shipped
``knowledge/relationship_manifest.json`` resolves against the Mnemos corpus through
the stdlib mirror to exactly the authored directed references — every pattern
``alternatives`` entry as one ``alternative`` edge and every rule
``recommended_pattern`` as one ``triggers`` edge — with no gap and nothing dropped.
The Othrys-side drift test binds the mirror's shape and normaliser to the reader's.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from mnemos.knowledge import relationship_manifest_mirror as mm


@pytest.fixture(scope="module")
def corpus() -> dict:
    return mm.load_corpus()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return mm.load_manifest()


def _authored(corpus: dict) -> set[tuple[str, str, str]]:
    alts = {("alternative", f"mnemos:{p['id']}", f"mnemos:{t}")
            for p in corpus["patterns"] for t in p.get("alternatives", [])}
    trig = {("triggers", f"mnemos:{r['id']}", f"mnemos:{r['recommended_pattern']}")
            for r in corpus["rules"] if r.get("recommended_pattern")}
    return alts | trig


def test_shipped_manifest_resolves_to_the_authored_directed_references(corpus):
    result = mm.check()
    assert {(v, s, t) for v, s, t, _p in result["edges"]} == _authored(corpus)
    assert result["gaps"] == []
    assert result["declared"] == result["materialized"] == 347 + 67


def test_resolution_is_idempotent(manifest, corpus):
    assert mm.resolve(manifest, corpus)["edges"] == mm.resolve(manifest, corpus)["edges"]


def test_an_alternative_naming_a_structure_id_fails_closed(manifest, corpus):
    """A structure id is not a pattern node, so a ``domain``-scope alternative that
    names one is a hard error — never a dropped link."""
    broken = copy.deepcopy(corpus)
    pattern = next(p for p in broken["patterns"] if p["id"] == "binary-search-tree-ops")
    pattern["alternatives"] = ["sorted-array-binary-search", "hashmap"]
    with pytest.raises(mm.DanglingTarget, match="mnemos:hashmap"):
        mm.resolve(manifest, broken)


def test_a_rule_naming_no_pattern_fails_closed(manifest, corpus):
    broken = copy.deepcopy(corpus)
    broken["rules"][0]["recommended_pattern"] = "no-such-pattern"
    with pytest.raises(mm.DanglingTarget):
        mm.resolve(manifest, broken)


def test_the_mirror_imports_no_othrys():
    text = Path(mm.__file__).read_text(encoding="utf-8")
    assert "import othrys" not in text and "from othrys" not in text
