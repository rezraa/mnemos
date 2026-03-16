# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""Mnemos Dashboard — FastAPI application serving the real-time monitoring UI."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from mnemos.dashboard.routes import router
from mnemos.dashboard.ws import manager, ws_router

app = FastAPI(title="Mnemos Dashboard", version="1.0.0")
app.include_router(router, prefix="/api")
app.include_router(ws_router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ---------------------------------------------------------------------------
# Event file watcher — polls events.jsonl and pushes new events to WebSocket
# ---------------------------------------------------------------------------

def _events_file() -> Path:
    env = os.environ.get("MNEMOS_MEMORY_DIR")
    base = Path(env) if env else Path.home() / ".mnemos" / "memory"
    return base / "events.jsonl"


async def _watch_events() -> None:
    """Poll the events.jsonl file for new lines and broadcast via WebSocket."""
    ef = _events_file()
    # Start from end of file if it exists
    offset = ef.stat().st_size if ef.exists() else 0

    while True:
        await asyncio.sleep(1)  # poll every second
        if not ef.exists():
            continue
        size = ef.stat().st_size
        if size <= offset:
            if size < offset:
                offset = 0  # file was truncated, reset
            continue
        try:
            with open(ef, "r", encoding="utf-8") as f:
                f.seek(offset)
                new_lines = f.read()
                offset = f.tell()
            for line in new_lines.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    # Build a summary for the activity feed
                    event.setdefault("summary", _event_summary(event))
                    await manager.broadcast(event)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass


def _event_summary(event: dict) -> str:
    """Generate a human-readable summary for the activity feed."""
    etype = event.get("type", "")
    if etype == "decision_logged":
        pattern = event.get("pattern", "?")
        ds = event.get("ds", "?")
        outcome = event.get("outcome", "?")
        return f"Decision: {pattern} + {ds} → {outcome}"
    elif etype == "regression_logged":
        pattern = event.get("pattern", "?")
        return f"Regression: {pattern} — {event.get('description', '')[:80]}"
    elif etype == "correction_logged":
        return f"Correction: {event.get('from', '?')} → {event.get('to', '?')}"
    elif etype == "context_bootstrapped":
        pid = event.get("project_id", "?")
        return f"Context bootstrapped: {pid}"
    elif etype == "plan_algorithm":
        signals = ", ".join(event.get("signals", [])[:3]) or "none"
        n = event.get("matched_rules_count", 0)
        return f"Plan: signals=[{signals}] → {n} rules matched, {event.get('candidates_count', 0)} candidates"
    elif etype == "review_complexity":
        pattern = event.get("pattern", "?")
        feasible = "feasible" if event.get("feasible", True) else "INFEASIBLE"
        return f"Review: {pattern} @ {event.get('complexity', '?')} → {feasible}"
    elif etype == "suggest_refactor":
        cur = event.get("current_pattern", "?")
        target = event.get("target_complexity", "any")
        n = event.get("suggestions_count", 0)
        return f"Refactor: {cur} → target {target}, {n} suggestions"
    return json.dumps(event)[:100]


@app.on_event("startup")
async def startup():
    """Start the event file watcher on dashboard startup."""
    asyncio.create_task(_watch_events())


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the single-page dashboard."""
    return (static_dir / "index.html").read_text()


def main(port: int = 8420):
    """Entry-point for ``python -m mnemos.dashboard.app``."""
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
