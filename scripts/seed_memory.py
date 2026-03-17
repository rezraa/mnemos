#!/usr/bin/env python3
# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Seed memory with realistic regressions for benchmark testing.

Populates the Mnemos MemoryStore with known regressions drawn from
real-world failure modes. These regressions are used by the benchmark
runner to test whether Mnemos-augmented responses correctly avoid
patterns that have historically caused problems.

Usage:
    python scripts/seed_memory.py [--memory-dir PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is importable when running from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from mnemos.memory.store import MemoryStore
from mnemos.memory.schemas import Regression, Severity


def seed(memory_dir: Path | None = None) -> int:
    """Seed regressions and return the count written."""
    store = MemoryStore(memory_dir=memory_dir)

    regressions = [
        Regression(
            pattern="quick-sort",
            ds="array",
            description=(
                "QuickSort on nearly-sorted data hit O(n^2) worst case in "
                "production, causing 30s timeout on n=500k input"
            ),
            severity=Severity.high,
            project_id="benchmark",
        ),
        Regression(
            pattern="floyd-warshall",
            ds="graph",
            description=(
                "Floyd-Warshall on V=10^5 graph caused OOM — V^3 = 10^15 "
                "operations is infeasible; should have used Dijkstra with "
                "priority queue for non-negative weights"
            ),
            severity=Severity.critical,
            project_id="benchmark",
        ),
        Regression(
            pattern="dp-lis",
            ds="dp",
            description=(
                "O(n^2) DP for Longest Increasing Subsequence with n=10^5 "
                "caused TLE. Use O(n log n) patience-sorting approach with "
                "binary search on tails array."
            ),
            severity=Severity.high,
            project_id="benchmark",
        ),
        Regression(
            pattern="dfs-traversal",
            ds="graph",
            description=(
                "Recursive DFS on graph with depth > 10^4 caused stack "
                "overflow. Use explicit stack or increase recursion limit."
            ),
            severity=Severity.high,
            project_id="benchmark",
        ),
        Regression(
            pattern="string-builder-accumulation",
            ds="string",
            description=(
                "Naive string concatenation in a loop caused O(n^2) runtime "
                "due to immutable string copies. Use StringBuilder or "
                "list-then-join pattern."
            ),
            severity=Severity.medium,
            project_id="benchmark",
        ),
        Regression(
            pattern="single-pass-complement-lookup",
            ds="hashmap",
            description=(
                "HashMap with poor hash function on adversarial input caused "
                "O(n) collision chains, degrading two-sum from O(n) to O(n^2). "
                "Consider sorted-input two-pointer approach when possible."
            ),
            severity=Severity.medium,
            project_id="benchmark",
        ),
    ]

    for reg in regressions:
        store.add_regression(reg)

    return len(regressions)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Mnemos memory with benchmark regressions."
    )
    parser.add_argument(
        "--memory-dir",
        type=Path,
        default=None,
        help="Override the memory directory (default: ~/.mnemos/memory)",
    )
    args = parser.parse_args()

    count = seed(memory_dir=args.memory_dir)
    print(f"Seeded {count} regressions into MemoryStore")


if __name__ == "__main__":
    main()
