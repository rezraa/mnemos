# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Decoupling firewall + coeus semantic-parity drift test (story-79321e96).

The Shape-C engine in Mnemos is a JUSTIFIED MIRROR of coeus.knowledge.loader, not
a shared import: Mnemos runs standalone and its runtime code MUST NOT import
coeus.*/othrys.* (the titan-decoupling firewall). This module proves both halves:

* ``TestImportFirewall`` -- no shipping module under ``src/mnemos`` imports coeus/
  othrys (static source scan);
* ``TestCoeusParity`` -- the mirror stays faithful: the ported primitives are
  SEMANTICALLY identical to coeus's. Skip-guarded when coeus is not importable
  (test-only; coeus is a sibling repo, never a shipping dependency) -- the ONE
  place a drift test may reach coeus, per council f1b39fbd.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import mnemos.knowledge.loader as m

_SRC = Path(m.__file__).resolve().parents[2]  # .../src


# ==========================================================================
# Import firewall — shipping code imports no coeus.*/othrys.*
# ==========================================================================

class TestImportFirewall:
    def _forbidden_imports(self, path: Path) -> list[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in ("coeus", "othrys"):
                        bad.append(f"import {a.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in ("coeus", "othrys"):
                    bad.append(f"from {node.module} import ...")
        return bad

    def test_no_coeus_or_othrys_import_in_shipping_code(self) -> None:
        offenders: dict[str, list[str]] = {}
        for py in sorted((_SRC / "mnemos").rglob("*.py")):
            bad = self._forbidden_imports(py)
            if bad:
                offenders[str(py.relative_to(_SRC))] = bad
        assert not offenders, f"firewall breach -- coeus/othrys imported in shipping code: {offenders}"

    def test_engine_module_imports_are_stdlib_and_local_only(self) -> None:
        """The engine module (loader.py) imports nothing from coeus/othrys. The
        docstring cites the mirror source by name for provenance -- that is a
        comment, not an import; the AST scan is what governs."""
        assert self._forbidden_imports(Path(m.__file__)) == []


# ==========================================================================
# Coeus semantic-parity drift test (test-only, skip-guarded)
# ==========================================================================

def _load_coeus():
    """Import coeus's engine, adding the sibling ``../coeus/src`` if needed.

    Test-only path injection -- coeus is a sibling repo, never a shipping
    dependency. Returns the module or None (caller skips)."""
    try:
        import coeus.knowledge.loader as c
        return c
    except ImportError:
        sibling = _SRC.parents[0].parent / "coeus" / "src"  # <repo>/../coeus/src
        if (sibling / "coeus" / "knowledge" / "loader.py").exists():
            sys.path.insert(0, str(sibling))
            try:
                import coeus.knowledge.loader as c
                return c
            except ImportError:
                return None
        return None


class TestCoeusParity:
    @pytest.fixture(scope="class")
    def c(self):
        coeus = _load_coeus()
        if coeus is None:
            pytest.skip("coeus not importable (sibling repo absent) -- drift test skip-guarded")
        return coeus

    def test_ceilings_and_floor_parity(self, c) -> None:
        assert (m._SEED_CAP, m._TOPK_CAP, m._CONFIDENCE_FLOOR) == \
               (c._SEED_CAP, c._TOPK_CAP, c._CONFIDENCE_FLOOR)

    def test_state_vocabulary_parity(self, c) -> None:
        assert (m.HIT, m.LOW_CONFIDENCE, m.NO_MATCH, m.DANGLING) == \
               (c.HIT, c.LOW_CONFIDENCE, c.NO_MATCH, c.DANGLING)

    def test_signal_id_hash_parity(self, c) -> None:
        for t in ["weighted-graph-shortest-path", "count occurrences", "x", "  spaced  "]:
            assert m._signal_id(t) == c._signal_id(t)

    def test_retrieval_result_contract_parity(self, c) -> None:
        import dataclasses as dc
        assert [f.name for f in dc.fields(m.RetrievalResult)] == \
               [f.name for f in dc.fields(c.RetrievalResult)]

    def test_deep_freeze_parity(self, c) -> None:
        src = {"a": [1, {"b": 2}], "c": "s"}
        mf, cf = m.deep_freeze(src), c.deep_freeze(src)
        assert type(mf).__name__ == type(cf).__name__ == "_FrozenDict"
        assert isinstance(mf["a"], tuple) and isinstance(cf["a"], tuple)
        for frozen in (mf, cf):
            with pytest.raises(TypeError):
                frozen["a"] = 1

    def test_facet_primitives_parity(self, c) -> None:
        cases_range = ["1-5", "3", "50+", "garbage", ""]
        assert [m._parse_team_range(x) for x in cases_range] == \
               [c._parse_team_range(x) for x in cases_range]
        facet, cons = {"team_size": "1-10", "scale": "startup"}, {"team_size": "3", "scale": "startup"}
        assert m.facet_matches(facet, cons) == c.facet_matches(facet, cons) is True
        assert m.facet_matches(facet, {"team_size": "3"}) == c.facet_matches(facet, {"team_size": "3"}) is False
        mixed = ["free text", {"team_size": "1-5"}]
        assert m.split_conditions(mixed) == c.split_conditions(mixed)

    def test_hydrate_envelope_contract_parity(self, c) -> None:
        """Behavioural parity of the OUTPUT CONTRACT: coeus's engine on coeus's
        corpus and mnemos's on mnemos's corpus emit the same-shaped envelope (same
        state vocabulary, same retrieval-block keys, int votes, frozen patterns).
        The corpora and fan-out edge differ by design; the CONTRACT does not."""
        c_kb = c.KnowledgeLoader()
        m_kb = m.KnowledgeLoader()
        # drive each engine with a real signal id from its OWN index -> a HIT
        c_sig = c_kb.get_signal_index()[0]["signal_id"]
        m_sig = m_kb.get_signal_index()[0]["signal_id"]
        cr = c_kb.hydrate([c_sig], k=5)
        mr = m_kb.hydrate([m_sig], k=5)
        assert cr.state in (c.HIT, c.LOW_CONFIDENCE) and mr.state in (m.HIT, m.LOW_CONFIDENCE)
        assert type(cr).__name__ == type(mr).__name__ == "RetrievalResult"
        if cr.patterns and mr.patterns:
            assert set(cr.patterns[0]["retrieval"]) == set(mr.patterns[0]["retrieval"]) == \
                   {"score", "direct_votes", "propagated_votes", "seed"}
            assert isinstance(cr.votes[cr.patterns[0]["id"]], int)
            assert isinstance(mr.votes[mr.patterns[0]["id"]], int)
