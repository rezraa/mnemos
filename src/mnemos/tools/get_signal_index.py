# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: get_signal_index

ONE read-only accessor over the Shape-C signal index, returning the UNIFORM NESTED
container — a dict of labelled signal-view group(s), one group per corpus. Mnemos
has a single corpus (the pattern-signal corpus), so the container is one group:
``{pattern_signals: [{signal_id, signal_text, pattern_ids}]}``, composed from the
one loader view (``kb.get_signal_index()``).

The agent (LLM) recognises a problem's structural signals against the labelled
surface in working memory, then passes the matched ``signal_id``s to the retrieval
engine (``loader.hydrate``). This tool only exposes the view; it performs no
matching itself (matching is the LLM's job / the frozen benchmark recognizer, never
a fuzzy keyword pass in shipping code).

WHY the uniform nested container (council ae492280 / m-5a5837da, user directive):
every Titan's front door returns the SAME shape — a dict of corpus-named
signal-view groups (Theia: ``{component_signals: [...], system_signals: [...]}``) —
so a future second corpus is a NEW group behind THIS SAME tool, never a new file or
a new tool (the ``_NamedIndex`` seam already supports a second view). The id column
(``pattern_ids``) already encodes each signal's corpus, so nesting keeps that typing
without a redundant per-node type tag (council: an unconsumed tag rots into a second
source of truth).
"""

from __future__ import annotations

from mnemos.tools._shared import get_knowledge

# The single corpus's group name. A future corpus becomes a NEW key here (a new
# group behind the same tool), never a new file or tool.
_PATTERN_SIGNALS = "pattern_signals"


def get_signal_index(conn: object = None) -> dict:
    """Return the deterministic signal-index view in the uniform nested container.

    Args:
        conn: Optional Kuzu/LadybugDB connection. ``None`` -> JSON singleton
            loader; a connection -> the graph-backed loader (same engine, both
            modes).

    Returns:
        ``{"pattern_signals": [{signal_id, signal_text, pattern_ids}, ...]}`` --
        the group sorted by ``signal_id`` with sorted ``pattern_ids`` (delegated to
        the one loader method), so the container serialises identically on every
        call.
    """
    kb = get_knowledge(conn)
    return {_PATTERN_SIGNALS: kb.get_signal_index()}
