# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""REST API routes for the Mnemos Dashboard."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query

from mnemos.memory.schemas import DecisionOutcome
from mnemos.memory.store import MemoryStore

router = APIRouter()

_store = MemoryStore()


def _parse_time_range(time_range: str | None) -> datetime | None:
    """Convert a time-range shorthand (1D, 1W, 1M, All) to a cutoff datetime."""
    if not time_range or time_range.upper() == "ALL":
        return None
    now = datetime.now(timezone.utc)
    mapping = {"1D": timedelta(days=1), "1W": timedelta(weeks=1), "1M": timedelta(days=30)}
    delta = mapping.get(time_range.upper())
    if delta is None:
        return None
    return now - delta


# ------------------------------------------------------------------
# KPI / stats
# ------------------------------------------------------------------

@router.get("/stats")
async def get_stats(time_range: Optional[str] = Query(None, description="1D, 1W, 1M, or All")):
    """KPI card data."""
    stats = _store.get_stats()
    decisions = _store.get_decisions()
    cutoff = _parse_time_range(time_range)

    if cutoff:
        decisions = [d for d in decisions if d.timestamp >= cutoff]
        total = len(decisions)
        accepted = sum(1 for d in decisions if d.outcome == DecisionOutcome.accepted)
        stats["total_decisions"] = total
        stats["accepted"] = accepted
        stats["accuracy_rate"] = round((accepted / total * 100) if total else 0.0, 2)

    # Active project count
    contexts = _store._load(_store.CONTEXTS_FILE)
    stats["active_projects"] = len(contexts)

    # Avg response time placeholder (would be computed from timestamps in production)
    stats["avg_response_ms"] = 42

    return stats


# ------------------------------------------------------------------
# Decisions
# ------------------------------------------------------------------

@router.get("/decisions")
async def list_decisions(
    project_id: Optional[str] = None,
    pattern: Optional[str] = None,
    outcome: Optional[str] = None,
    time_range: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Decision history with filters."""
    outcome_enum = DecisionOutcome(outcome) if outcome else None
    decisions = _store.get_decisions(project_id=project_id, pattern=pattern, outcome=outcome_enum)
    cutoff = _parse_time_range(time_range)
    if cutoff:
        decisions = [d for d in decisions if d.timestamp >= cutoff]

    # Sort newest first
    decisions.sort(key=lambda d: d.timestamp, reverse=True)
    total = len(decisions)
    page = decisions[offset : offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [d.model_dump(mode="json") for d in page],
    }


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str):
    """Single decision by ID."""
    all_decisions = _store.get_decisions()
    for d in all_decisions:
        if d.id == decision_id:
            return d.model_dump(mode="json")
    return {"error": "not found"}


# ------------------------------------------------------------------
# Patterns
# ------------------------------------------------------------------

@router.get("/patterns")
async def list_patterns(time_range: Optional[str] = None):
    """Pattern analytics — usage, distribution, accuracy."""
    stats = _store.get_pattern_stats()
    decisions = _store.get_decisions()
    cutoff = _parse_time_range(time_range)

    if cutoff:
        decisions = [d for d in decisions if d.timestamp >= cutoff]
        pattern_counts: Counter[str] = Counter()
        ds_counts: Counter[str] = Counter()
        pattern_outcomes: dict[str, Counter[str]] = {}

        for d in decisions:
            pattern_counts[d.pattern_chosen] += 1
            ds_counts[d.ds_chosen] += 1
            if d.pattern_chosen not in pattern_outcomes:
                pattern_outcomes[d.pattern_chosen] = Counter()
            pattern_outcomes[d.pattern_chosen][d.outcome.value] += 1

        stats = {
            "pattern_usage": dict(pattern_counts.most_common()),
            "ds_distribution": dict(ds_counts.most_common()),
            "pattern_outcomes": {p: dict(c) for p, c in pattern_outcomes.items()},
        }

    return stats


@router.get("/patterns/{pattern_name}")
async def get_pattern_stats(pattern_name: str):
    """Stats for a single pattern."""
    decisions = _store.get_decisions(pattern=pattern_name)
    regressions = _store.get_regressions(pattern=pattern_name)
    total = len(decisions)
    accepted = sum(1 for d in decisions if d.outcome == DecisionOutcome.accepted)

    return {
        "pattern": pattern_name,
        "total_uses": total,
        "accepted": accepted,
        "rejected": total - accepted - sum(1 for d in decisions if d.outcome == DecisionOutcome.regressed),
        "regressed": sum(1 for d in decisions if d.outcome == DecisionOutcome.regressed),
        "accuracy_rate": round((accepted / total * 100) if total else 0.0, 2),
        "regressions": [r.model_dump(mode="json") for r in regressions],
    }


# ------------------------------------------------------------------
# Projects
# ------------------------------------------------------------------

@router.get("/projects")
async def list_projects():
    """Active projects with their contexts."""
    raw = _store._load(_store.CONTEXTS_FILE)
    projects = []
    for ctx in raw:
        pid = ctx.get("project_id", "unknown")
        decisions = _store.get_decisions(project_id=pid)
        projects.append({
            "project_id": pid,
            "project_path": ctx.get("project_path", ""),
            "language": ctx.get("language", "unknown"),
            "total_decisions": len(decisions),
            "structures_count": len(ctx.get("structures_found", [])),
            "patterns_count": len(ctx.get("patterns_found", [])),
            "last_updated": ctx.get("last_updated"),
        })
    return {"items": projects}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Project detail with full context."""
    context = _store.get_context(project_id)
    if context is None:
        return {"error": "not found"}

    decisions = _store.get_decisions(project_id=project_id)
    regressions = _store.get_regressions(project_id=project_id)
    corrections = _store.get_corrections(project_id=project_id)

    return {
        "context": context.model_dump(mode="json"),
        "decisions_count": len(decisions),
        "regressions_count": len(regressions),
        "corrections_count": len(corrections),
        "recent_decisions": [d.model_dump(mode="json") for d in decisions[-10:]],
    }


# ------------------------------------------------------------------
# Regressions & corrections
# ------------------------------------------------------------------

@router.get("/regressions")
async def list_regressions(
    project_id: Optional[str] = None,
    pattern: Optional[str] = None,
    time_range: Optional[str] = None,
):
    """Active regressions."""
    regressions = _store.get_regressions(pattern=pattern, project_id=project_id)
    cutoff = _parse_time_range(time_range)
    if cutoff:
        regressions = [r for r in regressions if r.timestamp >= cutoff]

    regressions.sort(key=lambda r: r.timestamp, reverse=True)
    return {
        "total": len(regressions),
        "items": [r.model_dump(mode="json") for r in regressions],
    }


@router.get("/corrections")
async def list_corrections(
    project_id: Optional[str] = None,
    time_range: Optional[str] = None,
):
    """Correction log."""
    corrections = _store.get_corrections(project_id=project_id)
    cutoff = _parse_time_range(time_range)
    if cutoff:
        corrections = [c for c in corrections if c.timestamp >= cutoff]

    corrections.sort(key=lambda c: c.timestamp, reverse=True)
    return {
        "total": len(corrections),
        "items": [c.model_dump(mode="json") for c in corrections],
    }


# ------------------------------------------------------------------
# Memory health & knowledge coverage
# ------------------------------------------------------------------

@router.get("/memory/health")
async def memory_health():
    """Memory health metrics — file sizes, record counts, staleness."""
    stats = _store.get_stats()
    decisions_raw = _store._load(_store.DECISIONS_FILE)
    contexts_raw = _store._load(_store.CONTEXTS_FILE)

    # Find most recent decision timestamp
    latest = None
    for d in decisions_raw:
        ts = d.get("timestamp")
        if ts and (latest is None or str(ts) > str(latest)):
            latest = ts

    return {
        "decisions_count": stats["total_decisions"],
        "regressions_count": stats["total_regressions"],
        "corrections_count": stats["total_corrections"],
        "projects_count": len(contexts_raw),
        "latest_decision": latest,
        "store_directory": str(_store._dir),
        "health_status": "healthy" if stats["total_decisions"] > 0 else "empty",
    }


@router.get("/knowledge/coverage")
async def knowledge_coverage():
    """Knowledge coverage — which patterns and DS have been observed."""
    pattern_stats = _store.get_pattern_stats()
    contexts_raw = _store._load(_store.CONTEXTS_FILE)

    all_structures: Counter[str] = Counter()
    all_patterns: Counter[str] = Counter()
    for ctx in contexts_raw:
        for s in ctx.get("structures_found", []):
            all_structures[s.get("type", "unknown")] += 1
        for p in ctx.get("patterns_found", []):
            all_patterns[p.get("pattern", "unknown")] += 1

    return {
        "decision_patterns": pattern_stats.get("pattern_usage", {}),
        "decision_ds": pattern_stats.get("ds_distribution", {}),
        "codebase_structures": dict(all_structures),
        "codebase_patterns": dict(all_patterns),
        "total_unique_patterns": len(pattern_stats.get("pattern_usage", {})),
        "total_unique_ds": len(pattern_stats.get("ds_distribution", {})),
    }
