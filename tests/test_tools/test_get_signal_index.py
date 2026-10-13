# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""get_signal_index — reachability-by-construction + the compact nested container.

Mnemos exposes exactly ONE reachable signal-index tool returning the uniform nested
container (council ae492280 / m-5a5837da) with the compact inner shape (council
1e970338): ``{pattern_signals: {pattern_id: {signal_id: signal_text}}}``, projected by
the one mirrored ``loader.compact_signal_view`` from the one loader view.

What is bound here:

  * REACHABILITY-BY-CONSTRUCTION — the tool module holds exactly ONE public
    top-level function and ``server.py`` declares exactly one signal-index
    ``@mcp.tool``. The filename-keyed seed mints one graph tool per file keyed by the
    stem, so a single public function makes the second-function seed-drop
    (m-698d738c) impossible by construction.
  * LOSSLESS PROJECTION — flattening the compact view yields exactly the loader
    view's ``(signal_id, signal_text, owner)`` triples, and every served id hydrates.
    Retrieval reads the loader view, never this projection, so recall is unchanged
    by construction.
  * BYTE STABILITY — patterns and signals are emitted in sorted id order, so the
    serialised view (no ``sort_keys``) is identical across calls and across
    processes under different PYTHONHASHSEEDs: a cacheable prefix.

Firewall: imports only mnemos.* + stdlib. No live-DB access.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

from mnemos.knowledge.loader import KnowledgeLoader, compact_signal_view
from mnemos.tools import get_signal_index as gsi_mod
from mnemos.tools.get_signal_index import get_signal_index

_SRC = Path(inspect.getsourcefile(gsi_mod)).resolve().parents[2]  # .../src


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
# COMPACT NESTED CONTAINER — one corpus-named group, lossless projection
# ==========================================================================

def _triples_of_view(view: list[dict]) -> set[tuple[str, str, str]]:
    return {(e["signal_id"], e["signal_text"], pid) for e in view for pid in e["pattern_ids"]}


def _triples_of_compact(group: dict[str, dict[str, str]]) -> set[tuple[str, str, str]]:
    return {(sid, text, pid) for pid, signals in group.items() for sid, text in signals.items()}


class TestCompactContainer:
    def test_accessor_returns_the_one_named_group(self) -> None:
        view = get_signal_index()
        assert set(view) == {"pattern_signals"}, f"expected one corpus group, found {sorted(view)}"
        assert view["pattern_signals"], "the corpus group is empty"

    def test_compact_shape(self) -> None:
        for pid, signals in get_signal_index()["pattern_signals"].items():
            assert isinstance(pid, str) and isinstance(signals, dict) and signals
            assert all(isinstance(s, str) and isinstance(t, str) for s, t in signals.items())

    def test_round_trip_preserves_every_triple(self) -> None:
        """Flattening the compact view gives exactly the loader view's
        (signal_id, signal_text, owner) triples — nothing dropped, nothing invented."""
        compact = _triples_of_compact(get_signal_index()["pattern_signals"])
        assert compact == _triples_of_view(KnowledgeLoader().get_signal_index())

    def test_loader_view_is_exactly_recoverable(self) -> None:
        """Inverting the compact view rebuilds the loader view entry-for-entry — same
        order, same sorted ``pattern_ids`` lists — not merely the same set of triples."""
        rebuilt: dict[str, dict] = {}
        for pid, signals in get_signal_index()["pattern_signals"].items():
            for sid, text in signals.items():
                rebuilt.setdefault(sid, {"signal_id": sid, "signal_text": text, "pattern_ids": []})["pattern_ids"].append(pid)
        view = [{**e, "pattern_ids": sorted(e["pattern_ids"])} for _, e in sorted(rebuilt.items())]
        assert view == KnowledgeLoader().get_signal_index()

    def test_every_served_id_hydrates_to_its_owner(self) -> None:
        kb = KnowledgeLoader()
        for pid, signals in get_signal_index()["pattern_signals"].items():
            res = kb.hydrate([next(iter(signals))], k=1, fan_out=False)
            assert res.patterns and res.patterns[0]["id"] == pid

    def test_tool_is_the_mirrored_projection(self) -> None:
        """The tool adds nothing beyond the one projection the parity case binds."""
        assert get_signal_index() == {
            "pattern_signals": compact_signal_view(KnowledgeLoader().get_signal_index(), "pattern_ids")}

    def test_smaller_than_the_loader_view(self) -> None:
        compact = json.dumps(get_signal_index(), ensure_ascii=False)
        full = json.dumps({"pattern_signals": KnowledgeLoader().get_signal_index()}, ensure_ascii=False)
        assert len(compact) < 0.6 * len(full)


# ==========================================================================
# BYTE STABILITY — sorted emission, in-process and cross-process
# ==========================================================================

class TestByteStability:
    def test_patterns_and_signals_in_sorted_id_order(self) -> None:
        grp = get_signal_index()["pattern_signals"]
        assert list(grp) == sorted(grp)
        for signals in grp.values():
            assert list(signals) == sorted(signals)

    def test_byte_identical_across_calls(self) -> None:
        """No ``sort_keys``: the emitted order itself is deterministic."""
        assert len({json.dumps(get_signal_index()) for _ in range(3)}) == 1

    def test_byte_identical_across_pythonhashseed(self) -> None:
        snippet = (
            "import json,hashlib;"
            "from mnemos.tools.get_signal_index import get_signal_index as g;"
            "print(hashlib.sha256(json.dumps(g()).encode()).hexdigest())"
        )
        env = {**os.environ, "PYTHONPATH": str(_SRC)}
        outs = set()
        for seed in ("0", "1"):
            r = subprocess.run([sys.executable, "-c", snippet], stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, env={**env, "PYTHONHASHSEED": seed}, timeout=120)
            assert r.returncode == 0, r.stderr
            outs.add(r.stdout.strip())
        assert len(outs) == 1, f"compact view bytes moved across PYTHONHASHSEED: {outs}"


class TestCompactSignalView:
    _VIEW = [
        {"signal_id": "s2", "signal_text": "two", "rule_ids": ["b", "a"]},
        {"signal_id": "s1", "signal_text": "one", "rule_ids": ["b"]},
    ]

    def test_groups_by_the_named_owner_key_in_sorted_order(self) -> None:
        out = compact_signal_view(self._VIEW, "rule_ids")
        assert json.dumps(out) == json.dumps({"a": {"s2": "two"},
                                              "b": {"s1": "one", "s2": "two"}})

    def test_bytes_independent_of_view_order(self) -> None:
        fwd = compact_signal_view(self._VIEW, "rule_ids")
        rev = compact_signal_view(list(reversed(self._VIEW)), "rule_ids")
        assert json.dumps(fwd) == json.dumps(rev)

    def test_empty_view(self) -> None:
        assert compact_signal_view([], "pattern_ids") == {}
