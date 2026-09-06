# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""TYPED-INDEX proof for get_signal_index (story-17c8dc00, council ae492280 /
m-5a5837da; root cause m-698d738c).

*** THE NORTH STAR. *** Mnemos exposes exactly ONE reachable signal-index tool
returning the UNIFORM NESTED container — a dict of corpus-named signal-view
group(s), one group for Mnemos's single pattern-signal corpus:
``{pattern_signals: [{signal_id, signal_text, pattern_ids}]}`` — matching Theia's
proven nested shape, so every Titan's front door matches and a future corpus is a
NEW group behind THIS SAME tool (never a new file/tool).

What is bound here:

  * REACHABILITY-BY-CONSTRUCTION — the tool module holds exactly ONE public
    top-level function and ``server.py`` declares exactly one signal-index
    ``@mcp.tool``. The filename-keyed seed mints one graph tool per file keyed by the
    stem, so a single public function makes the second-function seed-drop
    (m-698d738c) impossible by construction.
  * UNIFORM CONTAINER — the accessor returns exactly ``{"pattern_signals": [...]}``
    with each entry carrying exactly ``{signal_id, signal_text, pattern_ids}`` (no
    per-node type tag — an unconsumed tag rots into a second source of truth).
  * DETERMINISM / NO-REGRESSION-BY-CONSTRUCTION — the group is sorted by
    ``signal_id`` with sorted ``pattern_ids``; the container is byte-identical across
    fresh calls; and its group is byte-identical to a fresh loader's list view (the
    tool only RESHAPES the one loader method, so the frozen mnemos-Gmetric recall —
    which reads the loader list — is identical by construction).

Firewall: imports only mnemos.* + stdlib. No live-DB access; the live-summon
reachability leg is the user's post-re-seed step.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from mnemos.knowledge.loader import KnowledgeLoader
from mnemos.tools import get_signal_index as gsi_mod
from mnemos.tools.get_signal_index import get_signal_index

_ENTRY_KEYS = {"signal_id", "signal_text", "pattern_ids"}


# ==========================================================================
# REACHABILITY-BY-CONSTRUCTION — one public fn, one @mcp.tool (the seed-drop fix)
# ==========================================================================

def _public_top_level_functions(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")]


def _mcp_tool_functions(path: Path) -> list[str]:
    """Names of module-level functions decorated with ``@mcp.tool(...)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in n.decorator_list:
            call = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(call, ast.Attribute) and call.attr == "tool" \
                    and isinstance(call.value, ast.Name) and call.value.id == "mcp":
                names.append(n.name)
    return names


class TestReachabilityByConstruction:
    def test_tool_module_has_exactly_one_public_function(self) -> None:
        """The filename-keyed seed mints ONE tool per file keyed by the stem; a single
        public function makes a second-function drop (m-698d738c) impossible."""
        fns = _public_top_level_functions(Path(inspect.getsourcefile(gsi_mod)))
        assert fns == ["get_signal_index"], f"expected one public fn, found {fns}"

    def test_server_declares_exactly_one_signal_index_tool(self) -> None:
        import mnemos.server as server
        tools = [t for t in _mcp_tool_functions(Path(inspect.getsourcefile(server))) if "signal_index" in t]
        assert tools == ["get_signal_index"], f"expected one signal-index @mcp.tool, found {tools}"


# ==========================================================================
# UNIFORM NESTED CONTAINER — one corpus-named group, exact entry keys
# ==========================================================================

class TestUniformContainer:
    def test_accessor_returns_the_one_named_group(self) -> None:
        view = get_signal_index()
        assert set(view) == {"pattern_signals"}, f"expected one corpus group, found {sorted(view)}"
        assert view["pattern_signals"], "the corpus group is empty"

    def test_each_entry_has_exactly_the_three_keys_no_type_tag(self) -> None:
        """No per-node type tag: the id column (pattern_ids) already encodes the
        corpus, so an extra tag would be an unconsumed second source of truth."""
        for entry in get_signal_index()["pattern_signals"]:
            assert set(entry) == _ENTRY_KEYS, f"unexpected entry keys {sorted(entry)}"


# ==========================================================================
# DETERMINISM / NO-REGRESSION-BY-CONSTRUCTION — reshape only
# ==========================================================================

class TestDeterminism:
    def test_group_sorted_by_signal_id_with_sorted_id_lists(self) -> None:
        entries = get_signal_index()["pattern_signals"]
        assert [e["signal_id"] for e in entries] == sorted(e["signal_id"] for e in entries)
        for e in entries:
            assert e["pattern_ids"] == sorted(e["pattern_ids"]), f"{e['signal_id']} pattern_ids unsorted"

    def test_container_byte_identical_across_fresh_calls(self) -> None:
        dumps = {json.dumps(get_signal_index(), sort_keys=True) for _ in range(3)}
        assert len(dumps) == 1

    def test_container_is_the_loader_view_only_reshaped(self) -> None:
        """Only presentation shape changed: the group re-presents the SAME frozen
        loader list under one label, so the mnemos-Gmetric recall (which reads the
        loader list) is identical by construction."""
        fresh = KnowledgeLoader()
        assert get_signal_index()["pattern_signals"] == fresh.get_signal_index()
