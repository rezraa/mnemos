#!/usr/bin/env python3
# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""
Gap analysis: compare extracted knowledge against comprehensive DSA taxonomy.

Identifies missing data structures, patterns, and structural categories
by comparing structures.json against a comprehensive taxonomy of DSA topics.

Usage:
    python scripts/gap_analysis.py [--knowledge-dir PATH]
"""

import argparse
import json
import sys
from pathlib import Path


# ── Comprehensive DSA Taxonomy ──────────────────────────────────────────
# This defines the "ground truth" of what a complete knowledge base should cover.

COMPREHENSIVE_STRUCTURES = {
    "array": {
        "name": "Array",
        "expected_patterns": [
            "two-pointer-convergent",
            "two-pointer-same-direction",
            "sliding-window-fixed",
            "sliding-window-variable",
            "binary-search",
            "prefix-sum",
            "kadanes-algorithm",
            "dutch-national-flag",
            "merge-intervals",
            "cyclic-sort",
            "in-place-rotation",
            "quick-select",
        ],
    },
    "string": {
        "name": "String",
        "expected_patterns": [
            "kmp-string-matching",
            "rabin-karp",
            "two-pointer-string",
            "expand-around-center",
            "string-builder-accumulation",
            "manachers-algorithm",
            "z-algorithm",
        ],
    },
    "hashmap": {
        "name": "HashMap",
        "expected_patterns": [
            "single-pass-complement-lookup",
            "frequency-aggregation",
            "grouping-by-key",
            "index-mapping",
            "cache-lookup",
            "prefix-sum-with-hashmap",
            "sliding-window-with-map",
        ],
    },
    "hashset": {
        "name": "HashSet",
        "expected_patterns": [
            "hashset-membership",
            "longest-consecutive-sequence",
            "set-algebra-operations",
        ],
    },
    "linked-list": {
        "name": "Linked List",
        "expected_patterns": [
            "ll-fast-slow-pointers",
            "ll-reversal",
            "ll-merge-sorted",
            "ll-dummy-sentinel",
            "ll-nth-from-end",
            "ll-partition",
        ],
    },
    "stack": {
        "name": "Stack",
        "expected_patterns": [
            "balanced-delimiters",
            "monotonic-stack",
            "expression-evaluation",
            "undo-operations",
            "min-max-stack",
            "dfs-explicit-stack",
        ],
    },
    "queue": {
        "name": "Queue / Deque",
        "expected_patterns": [
            "bfs-traversal",
            "multi-source-bfs",
            "task-scheduling",
            "sliding-window-maximum",
            "zero-one-bfs",
        ],
    },
    "heap": {
        "name": "Heap / Priority Queue",
        "expected_patterns": [
            "heap-top-k",
            "heap-merge-k-sorted",
            "two-heaps-median",
            "dijkstra",
        ],
    },
    "tree": {
        "name": "Tree",
        "expected_patterns": [
            "dfs-inorder",
            "dfs-preorder",
            "dfs-postorder",
            "bfs-level-order",
            "binary-search-tree-ops",
            "lowest-common-ancestor",
            "tree-construction",
            "path-sum-accumulation",
            "tree-depth-height",
            "tree-serialization",
            "trie-prefix-tree",
            "segment-tree",
            "fenwick-tree",
            "morris-traversal",
            "binary-lifting",
        ],
    },
    "graph": {
        "name": "Graph",
        "expected_patterns": [
            "bfs-shortest-unweighted",
            "dfs-graph-traversal",
            "topological-sort",
            "union-find-connectivity",
            "flood-fill",
            "bellman-ford",
            "floyd-warshall",
            "tarjan-scc",
            "kruskal-mst",
            "prim-mst",
            "bipartite-check",
            "a-star",
            "eulerian-path",
            "articulation-points",
        ],
    },
    "disjoint-set": {
        "name": "Disjoint Set (Union-Find)",
        "expected_patterns": [
            "uf-dynamic-connectivity",
            "uf-cycle-detection",
        ],
    },
    "dp": {
        "name": "Dynamic Programming",
        "expected_patterns": [
            "memoization-top-down",
            "tabulation-bottom-up",
            "state-compression-bitmask",
            "knapsack-01",
            "longest-common-subsequence",
            "edit-distance",
            "interval-dp",
            "digit-dp",
            "dp-on-trees",
            "state-machine-dp",
            "dp-lis",
            "convex-hull-trick",
            "divide-and-conquer-optimization",
        ],
    },
    "recursion-backtracking": {
        "name": "Recursion / Backtracking",
        "expected_patterns": [
            "subsets-generation",
            "permutations-generation",
            "combinations-generation",
            "constraint-satisfaction",
            "divide-and-conquer",
        ],
    },
    "bloom-filter": {
        "name": "Bloom Filter",
        "expected_patterns": [
            "bloom-pre-filter",
        ],
    },
    "skip-list": {
        "name": "Skip List",
        "expected_patterns": [
            "skip-list-ordered-ops",
        ],
    },
    "b-tree": {
        "name": "B-Tree",
        "expected_patterns": [
            "b-tree-disk-optimized",
        ],
    },
    "circular-buffer": {
        "name": "Circular Buffer",
        "expected_patterns": [
            "circular-buffer-streaming",
        ],
    },
    "suffix-array": {
        "name": "Suffix Array / Suffix Tree",
        "expected_patterns": [
            "suffix-array-substring-search",
        ],
    },
}

# Additional structural categories that should be covered
STRUCTURAL_CATEGORIES = [
    "pointer-based-traversal",
    "window-based-aggregation",
    "divide-and-conquer",
    "greedy-selection",
    "dynamic-programming",
    "backtracking-search",
    "graph-traversal",
    "tree-recursion",
    "hash-based-lookup",
    "sorting-and-ordering",
    "binary-search-space",
    "interval-processing",
    "string-matching",
    "union-find-grouping",
    "heap-based-selection",
    "monotonic-structure",
    "bit-manipulation",
    "mathematical-formula",
]


def load_json(path: Path) -> dict | None:
    """Load and parse a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def analyze_gaps(knowledge_dir: Path):
    """Compare structures.json against comprehensive taxonomy."""
    structures_data = load_json(knowledge_dir / "structures.json")
    if not structures_data:
        print("ERROR: Cannot load structures.json")
        sys.exit(1)

    # Build index of existing structures and patterns
    existing_structures: dict[str, set[str]] = {}
    all_existing_patterns: set[str] = set()

    for struct in structures_data.get("structures", []):
        sid = struct.get("id", "")
        patterns = {p.get("id", "") for p in struct.get("patterns", []) if p.get("id")}
        existing_structures[sid] = patterns
        all_existing_patterns.update(patterns)

    # ── Report ──────────────────────────────────────────────────────────
    print("=" * 70)
    print("  MNEMOS KNOWLEDGE BASE — GAP ANALYSIS")
    print("=" * 70)

    # 1. Missing structures
    print("\n[1] MISSING DATA STRUCTURES")
    print("-" * 40)
    missing_structures = []
    for sid, taxonomy in COMPREHENSIVE_STRUCTURES.items():
        if sid not in existing_structures:
            missing_structures.append(f"  MISSING: {taxonomy['name']} ({sid})")
    if missing_structures:
        for msg in missing_structures:
            print(msg)
    else:
        print("  All expected data structures are present.")

    # 2. Missing patterns per structure
    print("\n[2] MISSING PATTERNS PER STRUCTURE")
    print("-" * 40)
    total_expected = 0
    total_present = 0
    total_missing = 0

    for sid, taxonomy in COMPREHENSIVE_STRUCTURES.items():
        expected = set(taxonomy["expected_patterns"])
        present = existing_structures.get(sid, set())
        missing = expected - present
        extra = present - expected

        total_expected += len(expected)
        total_present += len(present & expected)
        total_missing += len(missing)

        if missing or extra:
            print(f"\n  {taxonomy['name']} ({sid}):")
            print(f"    Expected: {len(expected)}, Present: {len(present & expected)}, "
                  f"Missing: {len(missing)}, Extra: {len(extra)}")
            for p in sorted(missing):
                print(f"    MISSING: {p}")
            for p in sorted(extra):
                print(f"    EXTRA (not in taxonomy): {p}")
        else:
            print(f"  {taxonomy['name']}: COMPLETE ({len(expected)}/{len(expected)} patterns)")

    # 3. Coverage summary
    print("\n[3] COVERAGE SUMMARY")
    print("-" * 40)
    coverage_pct = (total_present / total_expected * 100) if total_expected > 0 else 0
    print(f"  Structures: {len(existing_structures)}/{len(COMPREHENSIVE_STRUCTURES)} "
          f"({len(existing_structures)/len(COMPREHENSIVE_STRUCTURES)*100:.0f}%)")
    print(f"  Patterns:   {total_present}/{total_expected} ({coverage_pct:.1f}%)")
    print(f"  Missing:    {total_missing} patterns across all structures")

    # 4. Patterns in knowledge base but not in taxonomy (potentially extra)
    print("\n[4] PATTERNS NOT IN TAXONOMY (may need addition)")
    print("-" * 40)
    all_expected = set()
    for taxonomy in COMPREHENSIVE_STRUCTURES.values():
        all_expected.update(taxonomy["expected_patterns"])

    unlisted = all_existing_patterns - all_expected
    if unlisted:
        for p in sorted(unlisted):
            # Find which structure it belongs to
            for sid, pids in existing_structures.items():
                if p in pids:
                    print(f"  {p} (in {sid})")
                    break
    else:
        print("  None — all patterns are in the taxonomy.")

    # 5. Structural category coverage
    print("\n[5] STRUCTURAL CATEGORY COVERAGE")
    print("-" * 40)

    # Check which categories are represented by existing pattern signals
    all_signals = set()
    for struct in structures_data.get("structures", []):
        for pattern in struct.get("patterns", []):
            for signal in pattern.get("structural_signals", []):
                all_signals.add(signal.lower().replace("-", " "))

    for category in STRUCTURAL_CATEGORIES:
        cat_words = set(category.replace("-", " ").split())
        # Check if any signal contains keywords from this category
        found = False
        for signal in all_signals:
            signal_words = set(signal.split())
            if cat_words & signal_words:
                found = True
                break
        status = "COVERED" if found else "POTENTIALLY MISSING"
        marker = "  " if found else "  >>>  "
        print(f"{marker}{category}: {status}")

    # 6. Decision rules coverage
    print("\n[6] DECISION RULES COVERAGE")
    print("-" * 40)
    rules_data = load_json(knowledge_dir / "decision_rules.json")
    if rules_data:
        rules = rules_data.get("rules", [])
        print(f"  Total decision rules: {len(rules)}")

        # Check which structures have rules pointing to them
        ruled_structures = set()
        ruled_patterns = set()
        for rule in rules:
            rs = rule.get("recommended_structure", "")
            rp = rule.get("recommended_pattern", "")
            if rs:
                ruled_structures.add(rs)
            if rp:
                ruled_patterns.add(rp)

        unreachable_structs = set(existing_structures.keys()) - ruled_structures
        if unreachable_structs:
            print(f"  Structures with no decision rules pointing to them:")
            for s in sorted(unreachable_structs):
                print(f"    - {s}")
        else:
            print("  All structures have at least one decision rule.")

        unreachable_patterns = all_existing_patterns - ruled_patterns
        # Only warn about patterns that are core (not niche)
        core_unreachable = {
            p for p in unreachable_patterns
            if not any(
                prefix in p
                for prefix in ["bloom-", "skip-", "b-tree-", "circular-", "suffix-"]
            )
        }
        if core_unreachable:
            print(f"\n  Core patterns with no decision rule ({len(core_unreachable)}):")
            for p in sorted(core_unreachable):
                print(f"    - {p}")
    else:
        print("  WARNING: Cannot load decision_rules.json")

    # Final summary
    print(f"\n{'='*70}")
    if total_missing == 0 and not missing_structures:
        print("  RESULT: Knowledge base is COMPREHENSIVE")
    else:
        print(f"  RESULT: {len(missing_structures)} missing structures, "
              f"{total_missing} missing patterns")
        print("  ACTION: Add missing items to structures.json")
    print(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(
        description="Gap analysis for Mnemos knowledge base"
    )
    parser.add_argument(
        "--knowledge-dir",
        type=Path,
        default=Path("/Users/rezamalik/Repos/mnemos/src/mnemos/knowledge"),
        help="Path to knowledge directory",
    )
    args = parser.parse_args()

    analyze_gaps(args.knowledge_dir)


if __name__ == "__main__":
    main()
