# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for the bootstrap_context tool."""

import pytest
from pathlib import Path
from unittest.mock import patch

from mnemos.memory.store import MemoryStore
from mnemos.tools.bootstrap_context import bootstrap_context


@pytest.fixture(autouse=True)
def _patch_memory(tmp_path: Path):
    """Monkey-patch the shared memory singleton to use a temp directory."""
    temp_store = MemoryStore(memory_dir=tmp_path)
    with patch("mnemos.tools._shared.memory", temp_store):
        yield temp_store


# ------------------------------------------------------------------
# Basic storage
# ------------------------------------------------------------------

def test_stores_context(_patch_memory):
    store: MemoryStore = _patch_memory

    result = bootstrap_context(
        project_path="/tmp/my-project",
        language="python",
        structures_found=[
            {"type": "hashmap", "location": "main.py", "usage": "caching"},
            {"type": "array", "location": "utils.py", "usage": "buffer"},
        ],
        patterns_found=[
            {"pattern": "sliding-window", "location": "algo.py"},
        ],
        runtime_constraints=["max memory 512MB", "async/await"],
    )

    assert result["stored"] is True
    assert "project_id" in result
    project_id = result["project_id"]

    # Verify the context was actually persisted.
    ctx = store.get_context(project_id)
    assert ctx is not None
    assert ctx.language == "python"
    assert len(ctx.structures_found) == 2
    assert len(ctx.patterns_found) == 1
    assert "512MB" in (ctx.runtime_constraints or "")


# ------------------------------------------------------------------
# Validation against knowledge base
# ------------------------------------------------------------------

def test_validates_known_structures():
    result = bootstrap_context(
        project_path="/tmp/kb-test",
        language="python",
        structures_found=[
            {"type": "hashmap", "location": "a.py", "usage": "lookup"},
            {"type": "array", "location": "b.py", "usage": "storage"},
        ],
        patterns_found=[
            {"pattern": "sliding-window-fixed", "location": "c.py"},
        ],
    )

    validated = result["validated"]
    # 'hashmap' and 'array' are standard structures in the KB.
    assert "hashmap" in validated["known_structures"] or "array" in validated["known_structures"], (
        f"Expected at least one known structure, got {validated}"
    )
    # 'sliding-window-fixed' is a known pattern ID in the KB.
    assert "sliding-window-fixed" in validated["known_patterns"], (
        f"Expected 'sliding-window-fixed' in known patterns, got {validated}"
    )


def test_flags_unknown_structures():
    result = bootstrap_context(
        project_path="/tmp/unknown-test",
        language="python",
        structures_found=[
            {"type": "quantum_entangler", "location": "q.py", "usage": "teleport"},
        ],
        patterns_found=[
            {"pattern": "flux_capacitor_sort", "location": "time.py"},
        ],
    )

    validated = result["validated"]
    unknown = validated.get("unknown", [])
    assert "quantum_entangler" in unknown, (
        f"Expected 'quantum_entangler' in unknown, got {unknown}"
    )
    assert "flux_capacitor_sort" in unknown, (
        f"Expected 'flux_capacitor_sort' in unknown, got {unknown}"
    )
