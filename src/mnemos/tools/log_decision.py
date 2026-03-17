# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""MCP tool: log_decision

Log an algorithmic decision and its outcome to persistent memory.
"""

from __future__ import annotations

from typing import Any

from mnemos.memory.schemas import (
    Correction,
    Decision,
    DecisionMode,
    DecisionOutcome,
    Regression,
    Severity,
)
from mnemos.tools._shared import emit_event, memory


def log_decision(
    mode: str,
    problem: str,
    pattern_chosen: str,
    ds_chosen: str,
    outcome: str,
    project_id: str | None = None,
    regression_details: str | None = None,
    correction_details: str | None = None,
) -> dict:
    """Log an algorithmic decision and its outcome to memory.

    Args:
        mode: Context — one of "plan", "review", "maintain".
        problem: What problem was being solved.
        pattern_chosen: Algorithm pattern selected.
        ds_chosen: Data structure selected.
        outcome: Result — one of "accepted", "rejected", "regressed".
        project_id: Optional project this decision belongs to.
        regression_details: Details if outcome is "regressed".
        correction_details: Details if the decision was later corrected
            (format: "original_pattern -> corrected_pattern: reason").

    Returns:
        ``{logged: true, decision_id: "d-xxxx"}`` on success.
    """
    # Resolve enums with fallback
    try:
        decision_mode = DecisionMode(mode)
    except ValueError:
        decision_mode = DecisionMode.plan

    try:
        decision_outcome = DecisionOutcome(outcome)
    except ValueError:
        decision_outcome = DecisionOutcome.accepted

    effective_project_id = project_id or "default"

    # 1. Create and persist the Decision
    decision = Decision(
        mode=decision_mode,
        problem_description=problem,
        pattern_chosen=pattern_chosen,
        ds_chosen=ds_chosen,
        outcome=decision_outcome,
        project_id=effective_project_id,
        regression_details=regression_details,
        correction_details=correction_details,
    )

    decision_id = memory.log_decision(decision)

    result: dict[str, Any] = {
        "logged": True,
        "decision_id": f"d-{decision_id}",
    }

    # 2. If outcome is "regressed" and details provided, also log a Regression
    if decision_outcome == DecisionOutcome.regressed and regression_details:
        regression = Regression(
            pattern=pattern_chosen,
            ds=ds_chosen,
            description=regression_details,
            severity=Severity.medium,
            project_id=effective_project_id,
            decision_id=decision_id,
        )
        reg_id = memory.add_regression(regression)
        result["regression_id"] = f"r-{reg_id}"

        emit_event("regression_logged", {
            "decision_id": decision_id,
            "regression_id": reg_id,
            "pattern": pattern_chosen,
            "ds": ds_chosen,
            "description": regression_details,
        })

    # 3. If correction_details provided, parse and log a Correction
    if correction_details:
        original, corrected, reason = _parse_correction(
            correction_details, pattern_chosen,
        )
        correction = Correction(
            original_pattern=original,
            corrected_pattern=corrected,
            reason=reason,
            project_id=effective_project_id,
            decision_id=decision_id,
        )
        corr_id = memory.add_correction(correction)
        result["correction_id"] = f"c-{corr_id}"

        emit_event("correction_logged", {
            "decision_id": decision_id,
            "correction_id": corr_id,
            "from": original,
            "to": corrected,
            "reason": reason,
        })

    # 4. Emit general decision event for dashboard
    emit_event("decision_logged", {
        "decision_id": decision_id,
        "mode": mode,
        "pattern": pattern_chosen,
        "ds": ds_chosen,
        "outcome": outcome,
        "project_id": effective_project_id,
    })

    return result


def _parse_correction(
    details: str,
    fallback_original: str,
) -> tuple[str, str, str]:
    """Parse correction_details string into (original, corrected, reason).

    Expected format: "original_pattern -> corrected_pattern: reason"
    Falls back gracefully if format doesn't match.
    """
    original = fallback_original
    corrected = ""
    reason = details

    if "->" in details:
        parts = details.split("->", 1)
        original = parts[0].strip()
        remainder = parts[1].strip()
        if ":" in remainder:
            corrected, reason = remainder.split(":", 1)
            corrected = corrected.strip()
            reason = reason.strip()
        else:
            corrected = remainder
            reason = "correction applied"
    elif ":" in details:
        corrected, reason = details.split(":", 1)
        corrected = corrected.strip()
        reason = reason.strip()
    else:
        corrected = details

    return original, corrected, reason
