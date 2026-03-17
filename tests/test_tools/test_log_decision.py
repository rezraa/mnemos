# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for the log_decision tool."""

import pytest
from pathlib import Path
from unittest.mock import patch

from mnemos.memory.store import MemoryStore
from mnemos.memory.schemas import DecisionOutcome
from mnemos.tools.log_decision import log_decision
from mnemos.tools import _shared


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    """Monkey-patch the shared memory singleton to use a temp directory."""
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store):
        yield temp_store


# ------------------------------------------------------------------
# Core logging
# ------------------------------------------------------------------

def test_logs_decision_successfully(_patch_memory):
    store: MemoryStore = _patch_memory

    result = log_decision(
        mode="plan",
        problem="Two sum problem",
        pattern_chosen="hash-lookup",
        ds_chosen="hashmap",
        outcome="accepted",
        project_id="proj-1",
    )

    assert result["logged"] is True
    assert "decision_id" in result
    assert result["decision_id"].startswith("d-")

    # Verify it was actually persisted.
    decisions = store.get_decisions(project_id="proj-1")
    assert len(decisions) == 1
    assert decisions[0].pattern_chosen == "hash-lookup"
    assert decisions[0].outcome == DecisionOutcome.accepted


def test_logs_regression_on_regressed_outcome(_patch_memory):
    store: MemoryStore = _patch_memory

    result = log_decision(
        mode="review",
        problem="Matrix multiply",
        pattern_chosen="nested-loop",
        ds_chosen="array",
        outcome="regressed",
        project_id="proj-2",
        regression_details="Timed out on n=50k",
    )

    assert result["logged"] is True
    assert "regression_id" in result
    assert result["regression_id"].startswith("r-")

    # Verify the regression was persisted.
    regressions = store.get_regressions(project_id="proj-2")
    assert len(regressions) == 1
    assert regressions[0].description == "Timed out on n=50k"
    assert regressions[0].pattern == "nested-loop"


def test_logs_correction(_patch_memory):
    store: MemoryStore = _patch_memory

    result = log_decision(
        mode="maintain",
        problem="Sorting large dataset",
        pattern_chosen="bubble-sort",
        ds_chosen="array",
        outcome="accepted",
        project_id="proj-3",
        correction_details="bubble-sort -> merge-sort: O(n^2) too slow for n>10k",
    )

    assert result["logged"] is True
    assert "correction_id" in result
    assert result["correction_id"].startswith("c-")

    corrections = store.get_corrections(project_id="proj-3")
    assert len(corrections) == 1
    assert corrections[0].original_pattern == "bubble-sort"
    assert corrections[0].corrected_pattern == "merge-sort"
    assert "too slow" in corrections[0].reason


# ------------------------------------------------------------------
# Event emission
# ------------------------------------------------------------------

def test_emits_event(_patch_memory):
    """log_decision should emit a 'decision_logged' event."""
    captured_events: list[tuple[str, dict]] = []

    def listener(event_name: str, payload: dict):
        captured_events.append((event_name, payload))

    # Temporarily register listener.
    _shared._event_listeners.append(listener)
    try:
        log_decision(
            mode="plan",
            problem="test event",
            pattern_chosen="x",
            ds_chosen="y",
            outcome="accepted",
            project_id="p",
        )

        event_names = [e[0] for e in captured_events]
        assert "decision_logged" in event_names, (
            f"Expected 'decision_logged' event, got {event_names}"
        )

        # The payload should contain the decision_id.
        decision_event = next(e for e in captured_events if e[0] == "decision_logged")
        assert "decision_id" in decision_event[1]
    finally:
        _shared._event_listeners.remove(listener)
