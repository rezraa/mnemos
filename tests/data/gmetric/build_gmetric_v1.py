# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Authoring builder for mnemos-Gmetric-v1 (story-63e99042, council f1b39fbd).

FROZEN, blind, corpus-blind algorithm/data-structure-selection benchmark.

This script is the PROVENANCE record of how the benchmark was authored. It emits
two byte-frozen artifacts and computes the method-independent denominators:

  * problems_blind_v1.json  -- the blind problems, their FROZEN verbatim query
    signals, and their gold pattern ids + roles. THIS is the benchmark data;
    the grader reads it (not this script) and re-verifies its sha256.
  * gmetric_v1.json         -- the frozen metric spec: the concept/alias map
    (per-gold verdict E/B/A + acceptable corpus ids + structure), the TWO
    distinct denominators (method-independent content + method-dependent
    matcher-reachable ceiling), the score definition, the register/class
    strata, and the reproducibility hashes. The three LOCKED legs are written
    here by set_locked_legs.py AFTER the baseline is read (never before).

Design authorities (do not re-litigate):
  * council f1b39fbd decisions 4 + 5; council bb55bb05 decisions 1 + 2.
  * d-6146f069 -- the paraphrase-only failure this must avoid: problems AND
    golds are recorded VERBATIM and byte-frozen; queries are authored BEFORE
    any grading and never tuned toward gold vocabulary after seeing results.
  * m-0364c120 / bb55bb05-decision-1 -- a retrieval miss is NOT a content gap.
    Content existence (E/B/A) is decided by DIRECT corpus check here; coverage
    is decided by the grader later. The two are never conflated.
  * m-e8ccb163 -- never a single pooled mean. Every number is stratified by
    query-class, register, and structure, and the finest split (class) is
    primary so a bimodal population cannot cancel into a null.

Firewall: imports nothing from othrys.* or coeus.*. Reads only the on-disk
mnemos corpus via a direct json.load (no live DB, no second-process open).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
KDIR = Path(__file__).resolve().parents[3] / "src" / "mnemos" / "knowledge"
PATTERN_FILE = "structures.json"
RULES_FILE = "decision_rules.json"
COMPLEX_FILE = "complexities.json"

# Corpus-freeze GENERATION selector (S2 re-freeze, council f1b39fbd). The benchmark
# DATA (problems, golds, verdicts) is generation-invariant -- only the corpus it
# freezes against moves (v1 = pre-migration, v2 = post decision_rules dissolution).
# Default "v1" preserves S0's provenance byte-for-byte; MNEMOS_GMETRIC_VERSION=v2
# re-emits the frozen artifacts against the migrated corpus. spec_id stays
# "mnemos-Gmetric-v1" -- the benchmark identity is unchanged; the filename + the
# freeze manifest's new corpus hashes carry the generation.
_VER = os.environ.get("MNEMOS_GMETRIC_VERSION", "v1")
_SUF = "" if _VER == "v1" else f"_{_VER}"   # unversioned S0 names keep their historical form on v1

PROBLEMS_OUT = HERE / f"problems_blind_{_VER}.json"
GMETRIC_OUT = HERE / f"gmetric_{_VER}.json"
# External, tamper-evident pin of every frozen artifact + loaded corpus file.
# Emitted LAST (after both artifacts exist). grade._verify_substrate reads its
# pins from HERE, never from gmetric_v1.json -- pinning the scored answer key
# inside the file it certifies would be circular trust (CWE-345). This manifest
# is the trust root: moving any pinned byte without regenerating it (a visible,
# version-controlled act) fails the grader closed.
FREEZE_MANIFEST_OUT = HERE / f"freeze_manifest{_SUF}.json"

# Verdict codes (method-independent concept existence in the 179-pattern canon).
E, B, A = "E", "B", "A"  # Exists standalone / Borderline embedded / Absent

# ---------------------------------------------------------------------------
# THE BLIND BENCHMARK.
#
# register: "prose" (problem-language / rule-prose idiom) or "token" (corpus
#   kebab-token vocabulary). qclass is the FINER, primary stratum:
#     PA = prose, rule-prose-aligned      -> the CURRENT matcher CAN answer
#     PB = prose, problem-language (blind) -> the matcher misses; the real target
#     TK = token, corpus kebab vocabulary  -> the matcher misses; engine target
#     CE = canon-edge probe (any register) -> deliberately probes canon coverage (Q5)
#
# query: the EXACT signal string(s) fed verbatim to match_structural_signals.
#   Authored before grading; NEVER tuned toward gold vocabulary afterward.
#
# golds: each is one CONCEPT the problem needs. canonical names it; role is its
#   fit; verdict is decided by DIRECT corpus check (below, re-validated); acc is
#   the acceptable corpus ids (naming/mechanism variants) that satisfy it. Only
#   E golds are scored; B and A are neutral (excluded from numerator AND
#   denominator) but recorded so content-coverage is measurable.
# ---------------------------------------------------------------------------

PROBLEMS: list[dict] = [
    # ===================== PA: prose, rule-prose-aligned (matcher answerable) =====================
    {
        "id": "P01", "qclass": "PA", "register": "prose",
        "problem": "Given a sorted array of integers and a target value, find two elements whose values sum to the target.",
        "query": ["Sorted input with pair satisfying arithmetic constraint"],
        "golds": [
            {"concept": "two-pointer convergent scan on sorted input", "canonical": "two-pointer-convergent", "role": "primary_fit", "verdict": E, "acc": ["two-pointer-convergent"]},
            {"concept": "single-pass complement lookup", "canonical": "single-pass-complement-lookup", "role": "constraint_alternative", "verdict": E, "acc": ["single-pass-complement-lookup"]},
            {"concept": "binary search for complement", "canonical": "binary-search", "role": "alternative", "verdict": E, "acc": ["binary-search"]},
        ],
    },
    {
        "id": "P02", "qclass": "PA", "register": "prose",
        "problem": "Count how many times each distinct value appears so you can make frequency-based decisions (mode, top-k, thresholds).",
        "query": ["Count occurrences of each element for frequency-based decisions"],
        "golds": [
            {"concept": "hash frequency map", "canonical": "frequency-aggregation", "role": "primary_fit", "verdict": E, "acc": ["frequency-aggregation"]},
            {"concept": "direct-indexed counting array", "canonical": "counting-array", "role": "alternative", "verdict": E, "acc": ["counting-array"]},
            {"concept": "trie-based frequency for string keys", "canonical": "trie-frequency", "role": "alternative", "verdict": E, "acc": ["trie-frequency"]},
        ],
    },
    {
        "id": "P03", "qclass": "PA", "register": "prose",
        "problem": "Check whether a string containing several kinds of brackets is correctly nested and balanced.",
        "query": ["Validate nested open/close delimiter matching"],
        "golds": [
            {"concept": "stack of open delimiters", "canonical": "balanced-delimiters", "role": "primary_fit", "verdict": E, "acc": ["balanced-delimiters"]},
            {"concept": "counter for a single delimiter type", "canonical": "counter-for-single-type", "role": "constraint_alternative", "verdict": E, "acc": ["counter-for-single-type"]},
        ],
    },
    {
        "id": "P04", "qclass": "PA", "register": "prose",
        "problem": "Produce an order to run build tasks so every task runs only after the tasks it depends on.",
        "query": ["For my build system I need to order tasks/items respecting dependency constraints in a DAG."],
        "golds": [
            {"concept": "topological sort", "canonical": "topological-sort", "role": "primary_fit", "verdict": E, "acc": ["topological-sort"]},
            {"concept": "DFS reverse-postorder ordering", "canonical": "dfs-graph-traversal", "role": "alternative", "verdict": E, "acc": ["dfs-graph-traversal"]},
        ],
    },
    {
        "id": "P05", "qclass": "PA", "register": "prose",
        "problem": "From a large stream keep the k biggest items seen so far, with k much smaller than the total.",
        "query": ["Find k largest/smallest elements from stream or collection"],
        "golds": [
            {"concept": "bounded top-k heap", "canonical": "heap-top-k", "role": "primary_fit", "verdict": E, "acc": ["heap-top-k"]},
            {"concept": "quickselect kth statistic", "canonical": "quick-select", "role": "alternative", "verdict": E, "acc": ["quick-select"]},
            {"concept": "full sort then slice", "canonical": "sorting", "role": "alternative", "verdict": E, "acc": ["sorting"]},
        ],
    },
    {
        "id": "P06", "qclass": "PA", "register": "prose",
        "problem": "Find the fewest moves from a start cell to a goal cell on a grid where every step costs the same.",
        "query": ["minimum steps in unweighted graph/grid"],
        "golds": [
            {"concept": "BFS on unweighted graph", "canonical": "bfs-shortest-unweighted", "role": "primary_fit", "verdict": E, "acc": ["bfs-shortest-unweighted", "bfs-traversal"]},
            {"concept": "Dijkstra (degenerate uniform weight)", "canonical": "dijkstra", "role": "alternative", "verdict": E, "acc": ["dijkstra"]},
        ],
    },
    {
        "id": "P07", "qclass": "PA", "register": "prose",
        "problem": "Pick a subset of items, each with a weight and value, to maximize value under a capacity, each item used at most once.",
        "query": ["Select items with cost/weight to reach target capacity/sum"],
        "golds": [
            {"concept": "0/1 knapsack DP", "canonical": "knapsack-01", "role": "primary_fit", "verdict": E, "acc": ["knapsack-01"]},
            {"concept": "exhaustive subset search", "canonical": "subsets-generation", "role": "alternative", "verdict": E, "acc": ["subsets-generation"]},
        ],
    },
    {
        "id": "P08", "qclass": "PA", "register": "prose",
        "problem": "Find the longest subsequence common to two strings.",
        "query": ["Align or compare two sequences optimally"],
        "golds": [
            {"concept": "LCS DP", "canonical": "longest-common-subsequence", "role": "primary_fit", "verdict": E, "acc": ["longest-common-subsequence"]},
            {"concept": "edit distance DP", "canonical": "edit-distance", "role": "alternative", "verdict": E, "acc": ["edit-distance"]},
        ],
    },
    {
        "id": "P09", "qclass": "PA", "register": "prose",
        "problem": "Determine whether a linked list loops back on itself, using O(1) extra space.",
        "query": ["Detect cycle in linked list or iterative sequence with O(1) memory."],
        "golds": [
            {"concept": "Floyd fast/slow pointers", "canonical": "ll-fast-slow-pointers", "role": "primary_fit", "verdict": E, "acc": ["ll-fast-slow-pointers"]},
            {"concept": "visited set", "canonical": "hashset-membership", "role": "constraint_alternative", "verdict": E, "acc": ["hashset-membership"]},
        ],
    },
    {
        "id": "P10", "qclass": "PA", "register": "prose",
        "problem": "Given a list of intervals, merge every group that overlaps into single intervals.",
        "query": ["Given scheduling data I must merge, insert, or analyze overlapping intervals."],
        "golds": [
            {"concept": "sort-by-start then merge", "canonical": "merge-intervals", "role": "primary_fit", "verdict": E, "acc": ["merge-intervals"]},
            {"concept": "sweep line over endpoints", "canonical": "sweep-line", "role": "alternative", "verdict": E, "acc": ["sweep-line"]},
        ],
    },
    {
        "id": "P11", "qclass": "PA", "register": "prose",
        "problem": "Support fast prefix lookups and autocomplete over a dictionary of words.",
        "query": ["Search words by prefix or build autocomplete"],
        "golds": [
            {"concept": "trie / prefix tree", "canonical": "trie-prefix-tree", "role": "primary_fit", "verdict": E, "acc": ["trie-prefix-tree"]},
            {"concept": "hash set of words", "canonical": "hashset-membership", "role": "alternative", "verdict": E, "acc": ["hashset-membership"]},
        ],
    },
    {
        "id": "P12", "qclass": "PA", "register": "prose",
        "problem": "As friendships are added one at a time, answer whether two people are already in the same group.",
        "query": ["connected components as edges are added dynamically"],
        "golds": [
            {"concept": "union-find / disjoint set", "canonical": "union-find-connectivity", "role": "primary_fit", "verdict": E, "acc": ["union-find-connectivity", "uf-dynamic-connectivity"]},
            {"concept": "recompute components by traversal", "canonical": "dfs-graph-traversal", "role": "alternative", "verdict": E, "acc": ["dfs-graph-traversal", "bfs-traversal"]},
        ],
    },

    # ===================== PB: prose, problem-language / blind (matcher misses) =====================
    {
        "id": "P13", "qclass": "PB", "register": "prose",
        "problem": "Given daily profit-and-loss values, some negative, find the contiguous stretch of days with the maximum total.",
        "query": ["What is the largest total I can get from a run of consecutive days of gains and losses?"],
        "golds": [
            {"concept": "Kadane running-sum-with-reset", "canonical": "kadanes-algorithm", "role": "primary_fit", "verdict": E, "acc": ["kadanes-algorithm"]},
            {"concept": "prefix sums with running minimum", "canonical": "prefix-sum", "role": "alternative", "verdict": E, "acc": ["prefix-sum"]},
            {"concept": "divide and conquer max crossing", "canonical": "divide-and-conquer-max-subarray", "role": "alternative", "verdict": E, "acc": ["divide-and-conquer-max-subarray"]},
        ],
    },
    {
        "id": "P14", "qclass": "PB", "register": "prose",
        "problem": "Find the longest stretch inside a word that reads the same forwards and backwards.",
        "query": ["Find the longest stretch inside a word that reads the same forwards and backwards."],
        "golds": [
            {"concept": "expand around each center", "canonical": "expand-around-center", "role": "primary_fit", "verdict": E, "acc": ["expand-around-center"]},
            {"concept": "Manacher linear-time", "canonical": "manachers-algorithm", "role": "alternative", "verdict": E, "acc": ["manachers-algorithm"]},
            {"concept": "interval DP on palindromes", "canonical": "dp-palindromic", "role": "alternative", "verdict": E, "acc": ["dp-palindromic"]},
        ],
    },
    {
        "id": "P15", "qclass": "PB", "register": "prose",
        "problem": "Find the cheapest route between two cities where each road has a positive travel cost.",
        "query": ["Find the cheapest route between two cities where each road has a positive travel cost."],
        "golds": [
            {"concept": "Dijkstra with priority queue", "canonical": "dijkstra", "role": "primary_fit", "verdict": E, "acc": ["dijkstra"]},
            {"concept": "Bellman-Ford relaxation", "canonical": "bellman-ford", "role": "alternative", "verdict": E, "acc": ["bellman-ford"]},
        ],
    },
    {
        "id": "P16", "qclass": "PB", "register": "prose",
        "problem": "Count how many contiguous stretches of a list of integers, which may be negative, add up to exactly K.",
        "query": ["Count how many contiguous stretches of a list of integers, which may be negative, add up to exactly K."],
        "golds": [
            {"concept": "prefix sum counts in a hash map", "canonical": "prefix-sum-with-hashmap", "role": "primary_fit", "verdict": E, "acc": ["prefix-sum-with-hashmap"]},
            {"concept": "plain prefix sum", "canonical": "prefix-sum", "role": "alternative", "verdict": E, "acc": ["prefix-sum"]},
        ],
    },
    {
        "id": "P17", "qclass": "PB", "register": "prose",
        "problem": "Given a jumbled bag of integers, how long is the longest run of consecutive whole numbers you can form?",
        "query": ["Given a jumbled bag of integers, how long is the longest run of consecutive whole numbers you can form?"],
        "golds": [
            {"concept": "consecutive sequence via set boundaries", "canonical": "longest-consecutive-sequence", "role": "primary_fit", "verdict": E, "acc": ["longest-consecutive-sequence"]},
            {"concept": "sort then scan neighbours", "canonical": "sorting-then-scanning", "role": "alternative", "verdict": E, "acc": ["sorting-then-scanning"]},
        ],
    },
    {
        "id": "P18", "qclass": "PB", "register": "prose",
        "problem": "For each day's temperature, report how many days you must wait until a warmer day.",
        "query": ["For each day's temperature, report how many days until a warmer day."],
        "golds": [
            {"concept": "monotonic stack of pending indices", "canonical": "monotonic-stack", "role": "primary_fit", "verdict": E, "acc": ["monotonic-stack"]},
        ],
    },
    {
        "id": "P19", "qclass": "PB", "register": "prose",
        "problem": "In a family tree, find the closest ancestor shared by two given people.",
        "query": ["In a family tree, find the closest ancestor shared by two given people."],
        "golds": [
            {"concept": "recursive LCA search", "canonical": "lowest-common-ancestor", "role": "primary_fit", "verdict": E, "acc": ["lowest-common-ancestor"]},
            {"concept": "binary lifting for repeated queries", "canonical": "binary-lifting", "role": "alternative", "verdict": E, "acc": ["binary-lifting"]},
        ],
    },
    {
        "id": "P20", "qclass": "PB", "register": "prose",
        "problem": "What is the length of the longest run of increasing values you can pick from a sequence, not necessarily adjacent?",
        "query": ["What is the length of the longest run of increasing values you can pick from a sequence, not necessarily adjacent?"],
        "golds": [
            {"concept": "patience-sorting LIS with binary search", "canonical": "dp-lis", "role": "primary_fit", "verdict": E, "acc": ["dp-lis"]},
            {"concept": "quadratic DP with predecessor", "canonical": "dp-n-squared", "role": "alternative", "verdict": E, "acc": ["dp-n-squared"]},
        ],
    },
    {
        "id": "P21", "qclass": "PB", "register": "prose",
        "problem": "List every possible way to choose any number of items from a set of distinct items.",
        "query": ["List every possible way to choose any number of items from a set."],
        "golds": [
            {"concept": "include/exclude recursion", "canonical": "subsets-generation", "role": "primary_fit", "verdict": E, "acc": ["subsets-generation"]},
            {"concept": "bitmask enumeration of subsets", "canonical": "bitmask-enumeration", "role": "alternative", "verdict": E, "acc": ["bitmask-enumeration"]},
        ],
    },
    {
        "id": "P22", "qclass": "PB", "register": "prose",
        "problem": "As a window of fixed width slides across a stream of numbers, report the biggest value in the window at each step.",
        "query": ["As a fixed-width window slides across a stream of numbers, report the biggest value in the window at each step."],
        "golds": [
            {"concept": "monotonic deque of candidates", "canonical": "sliding-window-maximum", "role": "primary_fit", "verdict": E, "acc": ["sliding-window-maximum", "monotonic-deque"]},
            {"concept": "heap with lazy deletion", "canonical": "heap-based-window", "role": "alternative", "verdict": E, "acc": ["heap-based-window"]},
        ],
    },
    {
        "id": "P23", "qclass": "PB", "register": "prose",
        "problem": "As roads are added between towns one at a time, detect the first road that closes a loop.",
        "query": ["As roads are added between towns one at a time, detect the first road that closes a loop."],
        "golds": [
            {"concept": "union-find cycle detection", "canonical": "uf-cycle-detection", "role": "primary_fit", "verdict": E, "acc": ["uf-cycle-detection"]},
            {"concept": "union-find connectivity", "canonical": "union-find-connectivity", "role": "alternative", "verdict": E, "acc": ["union-find-connectivity", "uf-dynamic-connectivity"]},
        ],
    },
    {
        "id": "P24", "qclass": "PB", "register": "prose",
        "problem": "Keep track of the middle value of a growing collection of numbers as each new number arrives.",
        "query": ["Keep track of the middle value of a growing collection of numbers as each new number arrives."],
        "golds": [
            {"concept": "two balanced heaps", "canonical": "two-heaps-median", "role": "primary_fit", "verdict": E, "acc": ["two-heaps-median"]},
            {"concept": "sorted array with binary insert", "canonical": "sorted-array-with-binary-insert", "role": "alternative", "verdict": E, "acc": ["sorted-array-with-binary-insert"]},
        ],
    },

    # ===================== TK: token / kebab corpus vocabulary (matcher misses) =====================
    {
        "id": "P25", "qclass": "TK", "register": "token",
        "problem": "Find the shortest contiguous block of a list that satisfies a running condition.",
        "query": ["contiguous-subarray-satisfying-constraint"],
        "golds": [
            {"concept": "variable sliding window", "canonical": "sliding-window-variable", "role": "primary_fit", "verdict": E, "acc": ["sliding-window-variable"]},
            {"concept": "prefix sum with hashmap", "canonical": "prefix-sum-with-hashmap", "role": "alternative", "verdict": E, "acc": ["prefix-sum-with-hashmap"]},
        ],
    },
    {
        "id": "P26", "qclass": "TK", "register": "token",
        "problem": "Find every position where a pattern occurs inside a text string.",
        "query": ["pattern-occurrence-in-text"],
        "golds": [
            {"concept": "KMP failure function", "canonical": "kmp-string-matching", "role": "primary_fit", "verdict": E, "acc": ["kmp-string-matching"]},
            {"concept": "Z-function", "canonical": "z-function", "role": "alternative", "verdict": E, "acc": ["z-function"]},
            {"concept": "Rabin-Karp / rolling hash", "canonical": "rabin-karp", "role": "alternative", "verdict": E, "acc": ["rabin-karp", "rolling-hash"]},
        ],
    },
    {
        "id": "P27", "qclass": "TK", "register": "token",
        "problem": "Count connected regions of equal cells in a 2D grid.",
        "query": ["connected-region-in-grid"],
        "golds": [
            {"concept": "flood fill", "canonical": "flood-fill", "role": "primary_fit", "verdict": E, "acc": ["flood-fill"]},
            {"concept": "union-find over cells", "canonical": "union-find-connectivity", "role": "alternative", "verdict": E, "acc": ["union-find-connectivity"]},
        ],
    },
    {
        "id": "P28", "qclass": "TK", "register": "token",
        "problem": "Split an array into m contiguous parts minimizing the largest part sum.",
        "query": ["minimize-the-maximum-value"],
        "golds": [
            {"concept": "binary search on the answer", "canonical": "binary-search-on-answer", "role": "primary_fit", "verdict": E, "acc": ["binary-search-on-answer"]},
            {"concept": "greedy feasibility check", "canonical": "greedy", "role": "alternative", "verdict": E, "acc": ["greedy"]},
        ],
    },
    {
        "id": "P29", "qclass": "TK", "register": "token",
        "problem": "Support range-sum queries with point updates on a dynamic array.",
        "query": ["range-query-with-point-or-range-updates"],
        "golds": [
            {"concept": "segment tree", "canonical": "segment-tree", "role": "primary_fit", "verdict": E, "acc": ["segment-tree"]},
            {"concept": "Fenwick / BIT", "canonical": "fenwick-tree", "role": "alternative", "verdict": E, "acc": ["fenwick-tree"]},
            {"concept": "sqrt decomposition", "canonical": "sqrt-decomposition", "role": "alternative", "verdict": E, "acc": ["sqrt-decomposition"]},
        ],
    },
    {
        "id": "P30", "qclass": "TK", "register": "token",
        "problem": "Least-cost path in a positively weighted graph.",
        "query": ["weighted-graph-shortest-path"],
        "golds": [
            {"concept": "Dijkstra with priority queue", "canonical": "dijkstra", "role": "primary_fit", "verdict": E, "acc": ["dijkstra"]},
            {"concept": "Bellman-Ford", "canonical": "bellman-ford", "role": "alternative", "verdict": E, "acc": ["bellman-ford"]},
        ],
    },
    {
        "id": "P31", "qclass": "TK", "register": "token",
        "problem": "Sort an array containing only three distinct values in place in a single pass.",
        "query": ["three-way-in-place-partitioning"],
        "golds": [
            {"concept": "Dutch national flag", "canonical": "dutch-national-flag", "role": "primary_fit", "verdict": E, "acc": ["dutch-national-flag"]},
            {"concept": "counting sort", "canonical": "counting-sort", "role": "alternative", "verdict": E, "acc": ["counting-sort"]},
        ],
    },
    {
        "id": "P32", "qclass": "TK", "register": "token",
        "problem": "Fewest insert / delete / replace edits to turn one string into another.",
        "query": ["minimum-operations-to-transform-sequence"],
        "golds": [
            {"concept": "edit distance DP", "canonical": "edit-distance", "role": "primary_fit", "verdict": E, "acc": ["edit-distance"]},
            {"concept": "LCS DP", "canonical": "longest-common-subsequence", "role": "alternative", "verdict": E, "acc": ["longest-common-subsequence"]},
        ],
    },
    {
        "id": "P33", "qclass": "TK", "register": "token",
        "problem": "Group words that are anagrams of one another.",
        "query": ["canonical-form-as-map-key"],
        "golds": [
            {"concept": "group by canonical key", "canonical": "grouping-by-key", "role": "primary_fit", "verdict": E, "acc": ["grouping-by-key"]},
            {"concept": "sort then group", "canonical": "sorting-then-grouping", "role": "alternative", "verdict": E, "acc": ["sorting-then-grouping"]},
        ],
    },
    {
        "id": "P34", "qclass": "TK", "register": "token",
        "problem": "Cheapest set of connections that links every node together.",
        "query": ["minimum-spanning-tree-via-sorted-edges"],
        "golds": [
            {"concept": "Kruskal MST", "canonical": "kruskal-mst", "role": "primary_fit", "verdict": E, "acc": ["kruskal-mst"]},
            {"concept": "Prim MST", "canonical": "prim-mst", "role": "alternative", "verdict": E, "acc": ["prim-mst"]},
        ],
    },

    # ===================== CE: canon-edge probes (Q5 content-coverage) =====================
    {
        "id": "P35", "qclass": "CE", "register": "prose",
        "problem": "Pick one item uniformly at random from a stream whose total length you do not know in advance.",
        "query": ["Pick one item uniformly at random from a stream whose total length is unknown in advance."],
        "golds": [
            {"concept": "reservoir sampling", "canonical": "reservoir-sampling", "role": "primary_fit", "verdict": A, "acc": []},
        ],
    },
    {
        "id": "P36", "qclass": "CE", "register": "prose",
        "problem": "Find the value that appears more than half the time in a list, using only constant extra memory.",
        "query": ["Find the value that appears more than half the time in a list, using only constant extra memory."],
        "golds": [
            {"concept": "Boyer-Moore majority vote (O(1) space)", "canonical": "boyer-moore-majority-vote", "role": "primary_fit", "verdict": A, "acc": []},
            {"concept": "hash frequency count (O(n) space, not the space-optimal mechanism)", "canonical": "frequency-aggregation", "role": "constraint_alternative", "verdict": B, "acc": ["frequency-aggregation"]},
        ],
    },
    {
        "id": "P37", "qclass": "CE", "register": "prose",
        "problem": "Find a route on a very large map quickly by using a distance estimate to guide the search toward the goal.",
        "query": ["Find a route on a very large map quickly using a distance estimate to guide the search toward the goal."],
        "golds": [
            {"concept": "A* heuristic search", "canonical": "a-star-search", "role": "primary_fit", "verdict": A, "acc": []},
            {"concept": "Dijkstra (uninformed, correct but not heuristic-guided)", "canonical": "dijkstra", "role": "constraint_alternative", "verdict": E, "acc": ["dijkstra"]},
        ],
    },
    {
        "id": "P38", "qclass": "CE", "register": "prose",
        "problem": "Find the peak of a function that rises then falls, by repeatedly narrowing the search range.",
        "query": ["Find the peak of a function that rises then falls by repeatedly narrowing the range."],
        "golds": [
            {"concept": "ternary search on a unimodal function", "canonical": "ternary-search", "role": "primary_fit", "verdict": A, "acc": []},
            {"concept": "binary search on answer (monotonic feasibility, not unimodal extremum)", "canonical": "binary-search-on-answer", "role": "constraint_alternative", "verdict": B, "acc": ["binary-search-on-answer"]},
        ],
    },
    {
        "id": "P39", "qclass": "CE", "register": "token",
        "problem": "Shuffle an array uniformly at random in place.",
        "query": ["uniform-random-in-place-permutation"],
        "golds": [
            {"concept": "Fisher-Yates shuffle", "canonical": "fisher-yates-shuffle", "role": "primary_fit", "verdict": A, "acc": []},
        ],
    },
    {
        "id": "P40", "qclass": "CE", "register": "prose",
        "problem": "Apply many 'add X to every element between positions i and j' updates, then read the final array once.",
        "query": ["Apply many range-add updates over positions, then read the final array once."],
        "golds": [
            {"concept": "difference array (range-add via boundary marks)", "canonical": "difference-array", "role": "primary_fit", "verdict": B, "acc": ["prefix-sum"]},
            {"concept": "Fenwick tree with range update", "canonical": "fenwick-tree", "role": "alternative", "verdict": E, "acc": ["fenwick-tree"]},
            {"concept": "segment tree with lazy range add", "canonical": "segment-tree", "role": "alternative", "verdict": E, "acc": ["segment-tree"]},
        ],
    },
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_dump(obj) -> str:
    """Deterministic byte-stable JSON: sorted keys, fixed separators, trailing newline."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> None:
    structures = json.loads((KDIR / PATTERN_FILE).read_text(encoding="utf-8"))["structures"]
    rules = json.loads((KDIR / RULES_FILE).read_text(encoding="utf-8"))["rules"]

    # corpus id universe + pattern -> structure map
    pat_struct: dict[str, str] = {}
    for s in structures:
        for p in s.get("patterns", []):
            pat_struct[p["id"]] = s["id"]
    corpus_ids = set(pat_struct)
    struct_ids = {s["id"] for s in structures}

    # ---- method-DEPENDENT matcher-reachable ceiling (its own meter) ----
    wired: set[str] = set()
    for r in rules:
        rp = r.get("recommended_pattern", "")
        if rp in corpus_ids:
            wired.add(rp)
        for alt in r.get("alternatives", []):
            if alt in corpus_ids:
                wired.add(alt)
    unreachable = corpus_ids - wired
    structs_reachable = sorted({s["id"] for s in structures
                                if any(p["id"] in wired for p in s.get("patterns", []))})

    # ---- validate the authored benchmark ----
    seen_pids: set[str] = set()
    errors: list[str] = []
    for prob in PROBLEMS:
        pid = prob["id"]
        if pid in seen_pids:
            errors.append(f"{pid}: duplicate problem id")
        seen_pids.add(pid)
        if not prob["query"] or not all(isinstance(q, str) and q.strip() for q in prob["query"]):
            errors.append(f"{pid}: empty/blank query signal")
        for g in prob["golds"]:
            v = g["verdict"]
            acc = g["acc"]
            if v == E:
                if not acc:
                    errors.append(f"{pid} '{g['canonical']}': E gold with empty acceptable ids")
                if g["canonical"] not in corpus_ids:
                    errors.append(f"{pid}: E canonical '{g['canonical']}' not a corpus pattern id")
                for cid in acc:
                    if cid not in corpus_ids:
                        errors.append(f"{pid}: E acc id '{cid}' not in corpus")
            elif v == B:
                # borderline: canonical is a concept name (may be absent); acc lists the
                # embedded/related corpus id(s) it is NOT a first-class pattern for.
                for cid in acc:
                    if cid not in corpus_ids:
                        errors.append(f"{pid}: B acc id '{cid}' not in corpus")
            elif v == A:
                # A-rubric: ABSENT == the concept has NO first-class corpus pattern id.
                # This is a pattern-id test, NOT a text-grep test: a prose name-drop in
                # another pattern's avoid_when (e.g. fisher-yates-shuffle is mentioned in
                # next-permutation-iterative.avoid_when) is a pointer, not an embedding,
                # and does NOT upgrade the gold to B. The benchmark scores whether the
                # right FIRST-CLASS pattern is retrieved; a concept with no first-class
                # pattern is unreachable by construction and is correctly A. (A and B are
                # both neutral -- excluded from numerator AND denominator -- so this label
                # governs only the Q5 content-coverage tally, never a scored number.)
                if acc:
                    errors.append(f"{pid} '{g['canonical']}': A gold must have empty acceptable ids (verified absent)")
                if g["canonical"] in corpus_ids:
                    errors.append(f"{pid}: A canonical '{g['canonical']}' unexpectedly IS a corpus id")
            else:
                errors.append(f"{pid}: bad verdict '{v}'")

    # Namespace invariant (enforces the baseline's method_note): the grader scores
    # pattern-id golds only, and the baseline excludes recommended_structure because
    # NO structure id is ever an acceptable_id. Prove it here rather than trust the
    # coincidence -- struct-vs-pattern id overlap exists ({bloom-filter, suffix-array})
    # but must never leak into a gold's acceptable set.
    gold_acc_ids = {cid for prob in PROBLEMS for g in prob["golds"] for cid in g["acc"]}
    ns_overlap = struct_ids & gold_acc_ids
    if ns_overlap:
        errors.append(f"structure id(s) present in gold acceptable_ids (namespace leak): {sorted(ns_overlap)}")

    if errors:
        raise SystemExit("BENCHMARK VALIDATION FAILED:\n  " + "\n  ".join(errors))

    # ---- build the frozen concept/alias map + tallies (method-independent) ----
    reach_map: list[dict] = []
    tally = {E: 0, B: 0, A: 0}
    # matcher-reachable ceiling over the E-golds of THIS benchmark
    e_gold_reachable = 0
    for prob in PROBLEMS:
        for g in prob["golds"]:
            v = g["verdict"]
            tally[v] += 1
            structure = pat_struct.get(g["canonical"]) if v == E else (
                pat_struct.get(g["acc"][0]) + " (embedded)" if (v == B and g["acc"]) else "__absent__")
            row = {
                "problem": prob["id"], "qclass": prob["qclass"], "register": prob["register"],
                "concept": g["concept"], "canonical": g["canonical"], "role": g["role"],
                "verdict": v, "acceptable_ids": g["acc"], "structure": structure,
            }
            if v == E:
                row["matcher_reachable"] = bool(set(g["acc"]) & wired)
                if row["matcher_reachable"]:
                    e_gold_reachable += 1
            reach_map.append(row)

    total_golds = sum(tally.values())
    reachable_denominator = tally[E]

    # ---- content coverage stratified by qclass (the pooled % mixes mainstream with edge probes;
    #      m-e8ccb163: report the split so the pooled number cannot lie) ----
    content_by_qclass: dict[str, dict] = {}
    for qc in ("PA", "PB", "TK", "CE"):
        rows = [r for r in reach_map if r["qclass"] == qc]
        t = {E: sum(1 for r in rows if r["verdict"] == E),
             B: sum(1 for r in rows if r["verdict"] == B),
             A: sum(1 for r in rows if r["verdict"] == A)}
        tot = sum(t.values())
        content_by_qclass[qc] = {"E": t[E], "B": t[B], "A": t[A], "total": tot,
                                 "coverage_E_over_total": round(t[E] / tot, 4) if tot else 0.0}
    mainstream = [r for r in reach_map if r["qclass"] in ("PA", "PB", "TK")]
    ms_E = sum(1 for r in mainstream if r["verdict"] == E)
    ms_tot = len(mainstream)
    absent_gaps = sorted({r["canonical"] for r in reach_map if r["verdict"] == A})
    borderline = sorted({r["canonical"] for r in reach_map if r["verdict"] == B})

    # ---- blind problems artifact (byte-frozen benchmark DATA) ----
    problems_blind = {
        "spec_id": "mnemos-Gmetric-v1",
        "story": "story-63e99042",
        "what": ("Blind, corpus-blind algorithm/DS-selection problems. Each carries its FROZEN "
                 "verbatim query signal(s) fed to retrieval and its gold concept ids. Recorded "
                 "verbatim and byte-frozen (d-6146f069): the grader reads THIS file and feeds "
                 "'query' to the method unchanged."),
        "n_problems": len(PROBLEMS),
        "registers": sorted({p["register"] for p in PROBLEMS}),
        "qclasses": sorted({p["qclass"] for p in PROBLEMS}),
        "problems": [
            {"id": p["id"], "qclass": p["qclass"], "register": p["register"],
             "problem": p["problem"], "query": p["query"],
             "golds": [{"concept": g["concept"], "canonical": g["canonical"],
                        "role": g["role"], "verdict": g["verdict"]} for g in p["golds"]]}
            for p in PROBLEMS
        ],
    }
    PROBLEMS_OUT.write_text(canonical_dump(problems_blind), encoding="utf-8")

    # ---- frozen metric spec ----
    gmetric = {
        "spec_id": "mnemos-Gmetric-v1",
        "story": "story-63e99042",
        "title": "Frozen blind algorithm/DS-selection retrieval scorecard for the Mnemos retrofit",
        "authored_by": "Mnemos",
        "status": "FROZEN",
        "design_authority": ["council f1b39fbd (decisions 4,5)", "council bb55bb05 (decisions 1,2)"],
        "one_line": ("Concept-level recall@10 over a method-independent reachable set of E-golds; "
                     "the S1 engine must beat the CURRENT match_structural_signals baseline on the "
                     "same set. Every number stratified by query-class, register, and structure."),
        "1_grader": {
            "type": "curated_concept_map",
            "decision": "Frozen deterministic concept/alias lookup, NOT a live LLM judge.",
            "why": ("A frozen map is a pure function -> 'compute twice, same score' holds byte-exactly. "
                    "The map pre-encodes naming/mechanism variants so a correct alternate id still counts."),
            "rule": ("A gold is COVERED@k iff the method's rank-ordered top-k pattern ids for that "
                     "problem intersect ANY of that gold's acceptable_ids. Only E golds are scored; "
                     "B and A are neutral (excluded from numerator AND denominator)."),
            "verbatim_query_contract": ("The grader feeds problems_blind_v1.json 'query' to "
                                        "match_structural_signals unchanged. No paraphrase layer (d-6146f069)."),
        },
        "2_denominators": {
            "note": "TWO denominators, kept strictly distinct (bb55bb05-decision-1). Never conflated.",
            "content_method_independent": {
                "definition": ("Does the gold concept EXIST in the 179-pattern canon, by DIRECT corpus "
                               "check? E=standalone pattern (or naming/mechanism variant); B=embedded/"
                               "borderline only; A=absent. This answers Q5 and is independent of any "
                               "retrieval method (m-0364c120: a miss is not a content gap)."),
                "tally": {"E_exists": tally[E], "B_borderline": tally[B], "A_absent": tally[A]},
                "total_golds": total_golds,
                "content_coverage_E_over_total": round(tally[E] / total_golds, 4),
                "content_coverage_by_qclass": content_by_qclass,
                "pooled_number_warning": ("The pooled 0.9059 mixes mainstream selection (PA/PB/TK) with "
                                          "deliberately-probed canon-edge cases (CE). Read the by_qclass "
                                          "split, not the pool (m-e8ccb163)."),
            },
            "matcher_reachable_ceiling_method_dependent": {
                "definition": ("Ceiling on what the CURRENT matcher could ever retrieve. Corpus-wide: a "
                               "pattern is reachable iff some rule names it as recommended_pattern or "
                               "alternative. An E-gold whose acceptable_ids are all unreachable is a "
                               "baseline retrieval-miss by construction, NOT a content gap."),
                "wired_patterns": len(wired),
                "unreachable_patterns": len(unreachable),
                "corpus_pattern_count": len(corpus_ids),
                "structures_with_reachable_pattern": len(structs_reachable),
                "structure_count": len(struct_ids),
                "benchmark_E_golds_matcher_reachable": e_gold_reachable,
                "benchmark_E_golds_total": reachable_denominator,
                "baseline_recall_ceiling": round(e_gold_reachable / reachable_denominator, 4) if reachable_denominator else 0.0,
            },
            "reachable_set_for_recall": {
                "definition": "recall denominator = E-golds only (B and A excluded, scored neutral).",
                "FROZEN_reachable_denominator": reachable_denominator,
            },
        },
        "3_score": {
            "metric": "concept_recall_at_k",
            "formula": "recall@k = (# E-golds whose acceptable_ids intersect the method's top-k) / E-golds",
            "primary_cutoff_k": 10,
            "secondary_cutoff_k": 5,
            "method_output_contract": ("Per problem the method emits a rank-ordered list of DISTINCT "
                                       "corpus pattern ids. BASELINE = match_structural_signals(query) -> "
                                       "for each matched rule in index order append recommended_pattern "
                                       "then alternatives, dedup preserving first-seen. AFTER (S1) = the "
                                       "ported signal-index engine over the SAME frozen queries + corpus."),
        },
        "4_stratification": {
            "rule": "m-e8ccb163: never a single pooled mean. The finest split (qclass) is primary.",
            "dimensions": {
                "qclass": {"PA": "prose, rule-prose-aligned (matcher answerable)",
                           "PB": "prose, problem-language / blind (matcher misses)",
                           "TK": "token, corpus kebab vocabulary (matcher misses; engine target)",
                           "CE": "canon-edge probe (Q5 content coverage)"},
                "register": ["prose", "token"],
                "structure": "parent structure of each E-gold's canonical id",
            },
        },
        "5_reproducibility": {
            "problems_blind": {"file": PROBLEMS_OUT.name, "sha256": sha(PROBLEMS_OUT)},
            "corpus_snapshot_sha256": {
                PATTERN_FILE: sha(KDIR / PATTERN_FILE),
                RULES_FILE: sha(KDIR / RULES_FILE),
                COMPLEX_FILE: sha(KDIR / COMPLEX_FILE),
            },
            "corpus_pattern_count": len(corpus_ids),
            "n_problems": len(PROBLEMS),
            "cutoffs": {"primary_k": 10, "secondary_k": 5},
            "recompute_contract": ("Given the pinned problems_blind hash, the corpus hashes, k, and this "
                                   "map, recall@k is a pure function of a method's ranked output -> "
                                   "identical on every recompute. Any hash change INVALIDATES the metric "
                                   "and forces a re-freeze (v1->v2) per migration tranche."),
        },
        "6_locked_legs": {
            "status": "SET_AFTER_BASELINE -> locked_legs_v1.json",
            "note": ("The three legs are calibrated from and frozen in locked_legs_v1.json AFTER the "
                     "baseline is read (never before). Kept external so this metric definition stays "
                     "reproducible from the builder alone; legs depend on the baseline, which depends "
                     "on this file."),
        },
        "Q5_answer_measured": {
            "question": "Is the 179-pattern canon high-coverage for these problems, or is there a genuine content gap?",
            "verdict": ("HIGH-COVERAGE for mainstream algorithm/DS selection; a small, named set of "
                        "specialized gaps at the canon edge. Measured, assumed neither way (m-0364c120)."),
            "mainstream_PA_PB_TK": {"E": ms_E, "total": ms_tot,
                                    "coverage": round(ms_E / ms_tot, 4) if ms_tot else 0.0,
                                    "reading": "every mainstream gold concept exists in the canon (0 content gaps)."},
            "canon_edge_CE": {"E": content_by_qclass["CE"]["E"], "B": content_by_qclass["CE"]["B"],
                              "A": content_by_qclass["CE"]["A"], "total": content_by_qclass["CE"]["total"],
                              "reading": "deliberately probed the boundary; this is where the gaps are."},
            "genuine_content_gaps_ABSENT": absent_gaps,
            "borderline_embedded_only": borderline,
            "scope_note": ("Per AC these gaps are RECORDED, not filled. Authoring new patterns is out of "
                           "scope for S0. The content denominator reflects the authored problem mix; the "
                           "mainstream classes were drawn from real selection problems (not reverse-"
                           "engineered from the corpus) and the edge probes from real specialized needs."),
        },
        "reachable_set_map": reach_map,
    }
    GMETRIC_OUT.write_text(canonical_dump(gmetric), encoding="utf-8")

    # ---- external tamper-evident freeze manifest (LAST: both artifacts now exist) ----
    # Pins the sha256 of BOTH frozen artifacts (problems_blind AND gmetric -- the scored
    # answer key + recall denominator live in gmetric, so it MUST be pinned externally)
    # plus the three loaded corpus files. grade._verify_substrate reads these pins and
    # fails closed on ANY drift, gmetric included; it never reads a pin from gmetric.
    freeze_manifest = {
        "spec_id": "mnemos-Gmetric-v1-freeze-manifest",
        "story": "story-63e99042",
        "what": ("External trust root for the frozen metric. Pins every artifact whose bytes "
                 "define the outcome gate: the blind problems, the scored concept/alias map + "
                 "recall denominator (gmetric_v1.json), and the three loaded corpus snapshots. "
                 "The grader verifies the on-disk substrate against THESE pins, never against a "
                 "pin stored inside gmetric_v1.json (which it grades against -- that would be "
                 "circular, CWE-345). Regenerating this manifest is the only way to move a pin, "
                 "and it is a visible, reviewable change in version control."),
        "hash_algo": "sha256",
        "pins": {
            PROBLEMS_OUT.name: sha(PROBLEMS_OUT),
            GMETRIC_OUT.name: sha(GMETRIC_OUT),
            PATTERN_FILE: sha(KDIR / PATTERN_FILE),
            RULES_FILE: sha(KDIR / RULES_FILE),
            COMPLEX_FILE: sha(KDIR / COMPLEX_FILE),
        },
    }
    FREEZE_MANIFEST_OUT.write_text(canonical_dump(freeze_manifest), encoding="utf-8")

    # ---- console ----
    print("=== mnemos-Gmetric-v1 authored ===")
    print(f"problems: {len(PROBLEMS)}  golds: {total_golds}  (E={tally[E]} B={tally[B]} A={tally[A]})")
    print(f"content coverage (E/total): {tally[E]}/{total_golds} = {tally[E]/total_golds:.4f}")
    print(f"reachable denominator (E-golds): {reachable_denominator}")
    print(f"matcher-reachable ceiling: {e_gold_reachable}/{reachable_denominator} "
          f"= {e_gold_reachable/reachable_denominator:.4f}" if reachable_denominator else "n/a")
    print(f"corpus wired/unreachable: {len(wired)}/{len(unreachable)}  of {len(corpus_ids)}")
    print("by qclass:")
    for qc in ("PA", "PB", "TK", "CE"):
        n = sum(1 for p in PROBLEMS if p["qclass"] == qc)
        eg = sum(1 for r in reach_map if r["qclass"] == qc and r["verdict"] == E)
        print(f"  {qc}: {n} problems, {eg} E-golds")
    print(f"wrote {PROBLEMS_OUT.name} sha256={sha(PROBLEMS_OUT)[:16]}...")
    print(f"wrote {GMETRIC_OUT.name} sha256={sha(GMETRIC_OUT)[:16]}...")
    print(f"wrote {FREEZE_MANIFEST_OUT.name} pinning {len(freeze_manifest['pins'])} files "
          f"sha256={sha(FREEZE_MANIFEST_OUT)[:16]}...")


if __name__ == "__main__":
    main()
