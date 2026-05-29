# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""E2/S6 hardening tests for mnemos log_decision.

Covers the failure shapes from the S5 post-mortem matrix: the ``notes`` ->
``correction_details`` alias, dropping the generated ``decision_id`` and the
unmodelled ``tags`` kwarg, and the fail-loud alias/canonical collision.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from mnemos.memory.store import MemoryStore
from mnemos.tools.log_decision import log_decision


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store):
        yield temp_store


_BASE = dict(
    mode="plan",
    problem="Two sum",
    pattern_chosen="hash-lookup",
    ds_chosen="hashmap",
    outcome="accepted",
)


def test_ignores_generated_decision_id():
    result = log_decision(decision_id="d-should-be-dropped", **_BASE)
    assert result["logged"] is True


def test_ignores_tags():
    result = log_decision(tags=["algo", "review"], **_BASE)
    assert result["logged"] is True


def test_notes_alias_maps_to_correction_details(_patch_memory):
    store: MemoryStore = _patch_memory
    result = log_decision(
        notes="hash-lookup -> two-pointer: better cache locality",
        **_BASE,
    )
    assert result["logged"] is True
    # correction_details was populated -> a Correction was logged.
    assert "correction_id" in result


def test_notes_and_correction_details_collision_raises():
    with pytest.raises(TypeError):
        log_decision(
            notes="alias value",
            correction_details="canonical value",
            **_BASE,
        )


def test_unknown_kwarg_still_raises():
    with pytest.raises(TypeError):
        log_decision(totally_unknown="boom", **_BASE)
