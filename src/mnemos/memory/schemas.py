# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""Pydantic models for all Mnemos memory types."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _short_id() -> str:
    """Generate a short random hex ID (8 chars)."""
    return os.urandom(4).hex()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DecisionOutcome(str, Enum):
    accepted = "accepted"
    rejected = "rejected"
    regressed = "regressed"


class DecisionMode(str, Enum):
    plan = "plan"
    review = "review"
    maintain = "maintain"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# ---------------------------------------------------------------------------
# Core memory models
# ---------------------------------------------------------------------------

class Decision(BaseModel):
    """A recorded algorithmic / DS decision."""

    id: str = Field(default_factory=_short_id, description="Unique decision identifier")
    timestamp: datetime = Field(default_factory=_now, description="When the decision was made")
    mode: DecisionMode = Field(..., description="Context in which the decision was made")
    problem_description: str = Field(..., description="What problem was being solved")
    pattern_chosen: str = Field(..., description="Algorithm pattern selected")
    ds_chosen: str = Field(..., description="Data structure selected")
    outcome: DecisionOutcome = Field(
        default=DecisionOutcome.accepted,
        description="Result of the decision",
    )
    project_id: str = Field(..., description="Project this decision belongs to")
    regression_details: Optional[str] = Field(
        default=None, description="Details if the decision caused a regression"
    )
    correction_details: Optional[str] = Field(
        default=None, description="Details if the decision was later corrected"
    )


class Regression(BaseModel):
    """A recorded regression caused by a pattern/DS choice."""

    id: str = Field(default_factory=_short_id, description="Unique regression identifier")
    timestamp: datetime = Field(default_factory=_now, description="When the regression was recorded")
    pattern: str = Field(..., description="Algorithm pattern that regressed")
    ds: str = Field(..., description="Data structure involved")
    description: str = Field(..., description="What went wrong")
    severity: Severity = Field(default=Severity.medium, description="How severe the regression is")
    project_id: str = Field(..., description="Project this regression belongs to")
    decision_id: Optional[str] = Field(
        default=None, description="Decision that caused this regression"
    )


class Correction(BaseModel):
    """A recorded correction from one pattern to another."""

    id: str = Field(default_factory=_short_id, description="Unique correction identifier")
    timestamp: datetime = Field(default_factory=_now, description="When the correction was made")
    original_pattern: str = Field(..., description="Pattern that was originally chosen")
    corrected_pattern: str = Field(..., description="Pattern it was corrected to")
    reason: str = Field(..., description="Why the correction was necessary")
    project_id: str = Field(..., description="Project this correction belongs to")
    decision_id: Optional[str] = Field(
        default=None, description="Decision that was corrected"
    )


# ---------------------------------------------------------------------------
# Codebase context models
# ---------------------------------------------------------------------------

class StructureFound(BaseModel):
    """A data structure found in the codebase."""

    type: str = Field(..., description="Type of structure (e.g. 'hash_map', 'tree')")
    location: str = Field(..., description="File/module where the structure lives")
    usage: str = Field(..., description="How the structure is used")


class PatternFound(BaseModel):
    """An algorithm pattern found in the codebase."""

    pattern: str = Field(..., description="Name of the pattern (e.g. 'sliding_window')")
    location: str = Field(..., description="File/module where the pattern appears")


class CodebaseContext(BaseModel):
    """Snapshot of a project's codebase for contextual recommendations."""

    project_id: str = Field(..., description="Unique project identifier")
    project_path: str = Field(..., description="Filesystem path to the project root")
    language: str = Field(default="python", description="Primary language of the project")
    structures_found: list[StructureFound] = Field(
        default_factory=list, description="Data structures discovered in the codebase"
    )
    patterns_found: list[PatternFound] = Field(
        default_factory=list, description="Algorithm patterns discovered in the codebase"
    )
    runtime_constraints: Optional[str] = Field(
        default=None, description="Known runtime/memory constraints"
    )
    last_updated: datetime = Field(default_factory=_now, description="When the context was last refreshed")


# ---------------------------------------------------------------------------
# Top-level aggregate (for whole-store serialisation if needed)
# ---------------------------------------------------------------------------

class MemoryStoreModel(BaseModel):
    """Aggregate of all memory data — useful for export/import."""

    decisions: list[Decision] = Field(default_factory=list)
    regressions: list[Regression] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)
    codebase_contexts: list[CodebaseContext] = Field(default_factory=list)
