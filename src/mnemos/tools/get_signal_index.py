# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: get_signal_index

ONE read-only accessor over the Shape-C signal index, returning the COMPACT
recognition view ``{pattern_signals: {pattern_id: {signal_id: signal_text}}}``
projected by ``loader.compact_signal_view`` from the one loader view
(``kb.get_signal_index()``).

The agent (LLM) recognises a problem's structural signals against the
``pattern_signals`` surface in working memory, then passes the matched ``signal_id``s
as ``matched_signal_ids`` to the retrieval tools (plan_algorithm / review_complexity),
which hydrate through the engine (``loader.hydrate``). This tool only exposes the
view; it performs no matching itself (matching is the LLM's job / the frozen
benchmark recognizer, never a fuzzy keyword pass in shipping code).

WHY nested by corpus group (council ae492280 / m-5a5837da): every Titan's front door
returns a dict of corpus-named signal-view groups, so a future second corpus is a NEW
group behind THIS SAME tool, never a new file or tool.

WHY this compact inner shape (council 1e970338): the whole view is read in-model on
every recognition, so its size is the recognition cost. Keying signals by their owning
pattern carries exactly what the loader view carries (the view is recoverable from it)
with no per-entry field names and no per-signal ``pattern_ids`` list. It is also a
cacheable prefix: patterns and signals are emitted in sorted id order and the view is
a pure function of the corpus, so every call on one corpus serialises to the same bytes.
"""

from __future__ import annotations

from mnemos.knowledge.loader import compact_signal_view
from mnemos.tools._shared import get_knowledge


def get_signal_index(conn: object = None) -> dict:
    """Return the compact, byte-stable signal-index view.

    Args:
        conn: Optional Kuzu/LadybugDB connection. ``None`` -> JSON singleton
            loader; a connection -> the graph-backed loader (same engine, both
            modes).

    Returns:
        ``{"pattern_signals": {pattern_id: {signal_id: signal_text}}}`` -- patterns
        in sorted id order, each pattern's signals in sorted id order. A signal
        owned by several patterns appears under each of them.
    """
    view = get_knowledge(conn).get_signal_index()
    return {"pattern_signals": compact_signal_view(view, "pattern_ids")}
