# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Caller constraint keys are checked against the facet catalogue (story-80d92a4b).

Measured live before this story: ``{'max_space': 'O(1)'}`` and ``{'N': 1e9}`` filtered
ZERO candidates on a query where the declared ``{'space': 'O(1)'}`` / ``{'n': 1e9}``
filter ten — and nothing told the caller its key was ignored. Every constraint-taking
tool now surfaces an undeclared key in its envelope, while a call that uses only
declared keys returns exactly what it returned before (no notice key at all).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from mnemos.knowledge.loader import FACET_CATALOGUE
from mnemos.memory.store import MemoryStore
from mnemos.tools.plan_algorithm import plan_algorithm
from mnemos.tools.review_complexity import review_complexity
from mnemos.tools.suggest_refactor import suggest_refactor

# The measured query: aho-corasick + bellman-ford signals -> a ten-candidate HIT.
_SIGS = [
    "sig-271aa405cfd3", "sig-82da6c89ef1e", "sig-d42df8f1dc84",
    "sig-03e41f276b04", "sig-a61838c922e5", "sig-b05ab56d0c69", "sig-e5c326306db1",
]
_NOTICE = "unknown_constraints"
_DECLARED = sorted(FACET_CATALOGUE.names)


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path):
    with patch("mnemos.tools._shared.memory", MemoryStore(memory_dir=tmp_path)):
        yield


def _plan(constraints):
    return plan_algorithm("p", _SIGS, constraints)


def _review(constraints):
    return review_complexity(detected_pattern="bellman-ford", detected_complexity="O(n^2)",
                             matched_signal_ids=_SIGS, constraints=constraints)


def _refactor(constraints):
    return suggest_refactor(current_pattern="bellman-ford", current_complexity="O(n^2)",
                            constraints=constraints)


_TOOLS = [_plan, _review, _refactor]


@pytest.mark.parametrize("misspelled,declared", [
    ({"max_space": "O(1)"}, {"space": "O(1)"}),
    ({"N": 1e9}, {"n": 1e9}),
])
def test_measured_case_declared_key_filters_misspelled_key_is_surfaced(misspelled, declared):
    """The measured defect, RED before this story: the misspelled key filters nothing
    and (now) says so; the declared key filters ten and carries no notice."""
    miss, hit = _plan(misspelled), _plan(declared)
    assert len(hit["filtered_out"]) == 10
    assert len(miss["filtered_out"]) == 0
    assert _NOTICE not in hit
    assert miss[_NOTICE] == {"keys": sorted(misspelled), "declared": _DECLARED}


@pytest.mark.parametrize("tool", _TOOLS)
def test_every_constraint_tool_surfaces_an_unknown_key(tool):
    res = tool({"max_space": "O(1)", "n": 1000})
    assert res[_NOTICE] == {"keys": ["max_space"], "declared": _DECLARED}


@pytest.mark.parametrize("tool", _TOOLS)
def test_unknown_key_is_surfaced_on_the_abstaining_path_too(tool):
    """The notice is retrieval-independent: a no_match call still carries it."""
    if tool is _plan:
        res = plan_algorithm("p", [], {"N": 5})
    elif tool is _review:
        res = review_complexity(detected_complexity="O(n)", constraints={"N": 5})
    else:
        res = suggest_refactor(current_pattern="no-such-pattern", constraints={"N": 5})
    assert res["retrieval_state"] == "no_match"
    assert res[_NOTICE]["keys"] == ["N"]


@pytest.mark.parametrize("tool", _TOOLS)
@pytest.mark.parametrize("constraints", [None, {}, {"n": 10**9}, {"input_size": 10**6},
                                         {"space": "O(1)"}, {"target_complexity": "O(n)"}])
def test_declared_keys_carry_no_notice(tool, constraints):
    assert _NOTICE not in tool(constraints)


@pytest.mark.parametrize("tool", _TOOLS)
def test_an_unknown_key_changes_nothing_but_the_notice(tool):
    """Adding an undeclared key leaves every other byte of the result as the
    declared-only call produced it — the check reports, it never re-ranks."""
    base = tool({"n": 100000})
    mixed = tool({"n": 100000, "N": 1})
    assert mixed.pop(_NOTICE)["keys"] == ["N"]
    mixed["constraints_analyzed"].pop("N")
    assert json.dumps(mixed, sort_keys=True) == json.dumps(base, sort_keys=True)


def test_non_string_and_oversized_keys_are_reported_bounded():
    from mnemos.tools._shared import _MAX_CONSTRAINT_VALUE_LEN

    res = _plan({7: 1, "x" * 10_000: 1})
    keys = res[_NOTICE]["keys"]
    assert keys == sorted(["7", "x" * _MAX_CONSTRAINT_VALUE_LEN])


# ── Constraint VALUES (story-0ed4bd1f) ───────────────────────────────────────
# Measured on the whole corpus before this story: {'space': 'o(1)'} filtered 10
# patterns where the declared 'O(1)' filters 151, and {'n': '1000000'} (a string)
# filtered 0 where 1000000 filters 10 — both silently. A value is now resolved
# against the catalogue: a case variant of a declared class, or an exact spelling of
# a whole number, normalises; anything else is surfaced and not applied.
_INVALID = "invalid_constraint_values"


def _corpus_filtered(constraints) -> int:
    from mnemos.knowledge.loader import KnowledgeLoader

    kb = KnowledgeLoader()
    return len(kb.filter_by_constraints(kb.get_all_patterns(), constraints)[1])


@pytest.mark.parametrize("variant,canonical,filtered", [
    ({"space": "o(1)"}, {"space": "O(1)"}, 151),
    ({"n": "1000000"}, {"n": 1000000}, 10),
])
def test_measured_value_cases_filter_as_their_canonical_value(variant, canonical, filtered):
    assert _corpus_filtered(canonical) == filtered
    assert _corpus_filtered(variant) == filtered


def _without_echo(res: dict) -> str:
    res = dict(res)
    res.pop("constraints_analyzed")
    return json.dumps(res, sort_keys=True)


@pytest.mark.parametrize("tool", _TOOLS)
@pytest.mark.parametrize("variant,canonical", [
    ({"space": "o(1)"}, {"space": "O(1)"}),
    ({"target_complexity": " o(N LOG N) "}, {"target_complexity": "O(n log n)"}),
    ({"n": "1000000"}, {"n": 1000000}),
    ({"input_size": "100000"}, {"n": 100000}),
    ({"n": 1e6}, {"n": 1000000}),
])
def test_a_normalised_value_returns_what_its_canonical_value_returns(tool, variant, canonical):
    res = tool(variant)
    assert _INVALID not in res and _NOTICE not in res
    assert _without_echo(res) == _without_echo(tool(canonical))


_O_CLASSES = ["O(1)", "O(log n)", "O(sqrt(n))", "O(n)", "O(n log n)", "O(n * sqrt(n))",
              "O(n^2)", "O(n^2 log n)", "O(n^3)", "O(2^n)", "O(n!)", "O(n^n)"]


@pytest.mark.parametrize("tool", _TOOLS)
@pytest.mark.parametrize("constraints,spelling,report", [
    ({"space": "O(V+E)"}, "space", {"value": "O(V+E)", "allowed": _O_CLASSES}),
    ({"space": "O(1) amortized"}, "space", {"value": "O(1) amortized", "allowed": _O_CLASSES}),
    ({"target_complexity": "linear"}, "target_complexity", {"value": "linear", "allowed": _O_CLASSES}),
    ({"space": ""}, "space", {"value": "", "allowed": _O_CLASSES}),
    ({"n": "abc"}, "n", {"value": "abc", "example": 1000000}),
    ({"n": "1-5"}, "n", {"value": "1-5", "example": 1000000}),
    ({"input_size": "10+"}, "input_size", {"value": "10+", "example": 1000000}),
    ({"n": -5}, "n", {"value": -5, "example": 1000000}),
    ({"n": 1.5}, "n", {"value": 1.5, "example": 1000000}),
    ({"n": True}, "n", {"value": True, "example": 1000000}),
    ({"n": [10]}, "n", {"value": "<list>", "example": 1000000}),
])
def test_an_invalid_value_is_surfaced_and_not_applied(tool, constraints, spelling, report):
    """Fail open: an invalid value is reported and the result is exactly the
    unconstrained one — never a silent wrong filter."""
    res = tool(constraints)
    notice = res.pop(_INVALID)
    assert list(notice) == [spelling]
    assert notice[spelling].pop("reason")
    assert notice[spelling] == report
    assert _NOTICE not in res
    assert _without_echo(res) == _without_echo(tool({}))


def test_an_invalid_value_leaves_a_valid_one_applied():
    res, base = _plan({"n": "abc", "space": "o(1)"}), _plan({"space": "O(1)"})
    assert list(res.pop(_INVALID)) == ["n"]
    assert _without_echo(res) == _without_echo(base)


def test_an_invalid_value_does_not_crash_feasibility():
    """Before this story a non-numeric n reached ``int(n)`` in review_complexity."""
    res = review_complexity(detected_complexity="O(n^2)", constraints={"n": "abc"})
    assert res["feasibility"]["is_feasible"] is True
    assert "not flagged" in res["feasibility"]["reason"]
    assert list(res[_INVALID]) == ["n"]


def test_suggest_refactor_surfaces_an_invalid_target_argument():
    """The ``target_complexity`` argument reaches the same gate, so it is resolved too."""
    miss = suggest_refactor(current_pattern="bellman-ford", current_complexity="O(n^2)",
                            target_complexity="o(n log n)")
    hit = suggest_refactor(current_pattern="bellman-ford", current_complexity="O(n^2)",
                           target_complexity="O(n log n)")
    assert json.dumps(miss, sort_keys=True).replace("o(n log n)", "O(n log n)") == \
        json.dumps(hit, sort_keys=True)
    bad = suggest_refactor(current_pattern="bellman-ford", current_complexity="O(n^2)",
                           target_complexity="fast")
    assert list(bad[_INVALID]) == ["target_complexity"]


def test_oversized_invalid_value_is_echoed_bounded():
    from mnemos.knowledge.facet_catalogue_mirror import MAX_VALUE_CHARS

    res = _plan({"space": "O" * 10_000})
    assert res[_INVALID]["space"]["value"] == "O" * MAX_VALUE_CHARS
