# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: get_signal_index

Thin, read-only accessor over the Shape-C signal index. Returns the
deterministic, byte-reproducible view of every structural signal in the corpus
as ``{signal_id, signal_text, pattern_ids}``.

The agent (LLM) recognises a problem's structural signals against this view in
working memory, then passes the matched ``signal_id``s to the retrieval engine
(``loader.hydrate`` -- wired to the tools in S3-S5). This tool only exposes the
index; it performs no matching itself (matching is the LLM's job / the frozen
benchmark recognizer, never a fuzzy keyword pass in shipping code).
"""

from __future__ import annotations

from mnemos.tools._shared import get_knowledge


def get_signal_index(conn: object = None) -> dict:
    """Return the deterministic signal-index view.

    Args:
        conn: Optional Kuzu/LadybugDB connection. ``None`` -> JSON singleton
            loader; a connection -> the graph-backed loader (same engine, both
            modes).

    Returns:
        ``{"signals": [{signal_id, signal_text, pattern_ids}, ...], "count": N}``
        -- sorted by ``signal_id`` with sorted ``pattern_ids`` so it serialises
        identically on every call.
    """
    kb = get_knowledge(conn)
    signals = kb.get_signal_index()
    return {"signals": signals, "count": len(signals)}
