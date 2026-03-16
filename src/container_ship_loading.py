# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""
Container Ship Loading — Meet-in-the-Middle Solution

Problem: N containers with weights, two holds. Weight difference between
holds must be <= D. Maximize total weight loaded. N up to 30, weights up to 10^9.

Approach: Meet in the middle. Split containers into two halves. For each half,
enumerate all 3^(N/2) assignments (each item: skip / hold1 / hold2). Track
(total_loaded, difference) where difference = hold1_weight - hold2_weight.
Combine halves: for each second-half state, binary search first-half states
for compatible differences, and query max total in that range.

Time:  O(3^(N/2) * N)  ≈ 14.3M * 15 ≈ 215M ops (feasible)
Space: O(3^(N/2))      ≈ 14.3M entries
"""

from bisect import bisect_left, bisect_right
from itertools import product


def max_cargo(weights: list[int], max_diff: int) -> int:
    n = len(weights)
    if n == 0:
        return 0

    mid = n // 2
    left_weights = weights[:mid]
    right_weights = weights[mid:]

    def enumerate_half(ws: list[int]) -> list[tuple[int, int]]:
        """
        Enumerate all assignments for a half.
        Each item can be: skipped (0), hold1 (+w), hold2 (-w for diff).
        Returns list of (total_loaded, diff) where diff = sum_hold1 - sum_hold2.
        """
        m = len(ws)
        results = []
        # Use iterative enumeration over 3^m states
        # Represent each state as a tuple of choices: 0=skip, 1=hold1, 2=hold2
        # For m up to 15, 3^15 = 14_348_907 which is fine
        if m == 0:
            return [(0, 0)]

        # Iterative approach using base-3 counting
        total_states = 3 ** m
        for state in range(total_states):
            total = 0
            diff = 0
            s = state
            for i in range(m):
                choice = s % 3
                s //= 3
                if choice == 1:  # hold1
                    total += ws[i]
                    diff += ws[i]
                elif choice == 2:  # hold2
                    total += ws[i]
                    diff -= ws[i]
            results.append((total, diff))
        return results

    # Enumerate left half
    left_states = enumerate_half(left_weights)

    # For efficient range queries: group by diff, sort, build prefix max of total
    # Sort left_states by diff
    left_states.sort(key=lambda x: x[1])

    # Extract sorted diffs and corresponding totals
    left_diffs = [s[1] for s in left_states]
    left_totals = [s[0] for s in left_states]

    # Build prefix max array: prefix_max[i] = max(left_totals[0..i])
    sz = len(left_states)
    prefix_max = [0] * sz
    prefix_max[0] = left_totals[0]
    for i in range(1, sz):
        prefix_max[i] = max(prefix_max[i - 1], left_totals[i])

    # suffix_max[i] = max(left_totals[i..sz-1])  (not needed if we use prefix_max on range)
    # Actually for a range [lo, hi], max = we need a structure. Let's just use
    # prefix_max and suffix_max together, or a sparse table.
    # Simpler: suffix_max
    suffix_max = [0] * sz
    suffix_max[sz - 1] = left_totals[sz - 1]
    for i in range(sz - 2, -1, -1):
        suffix_max[i] = max(suffix_max[i + 1], left_totals[i])

    # For a range query [lo, hi], we need max of left_totals[lo..hi].
    # With prefix_max and suffix_max alone we can't do arbitrary range max.
    # Let's build a sparse table for O(1) range max queries.

    import math

    if sz > 0:
        LOG = max(1, int(math.log2(sz)) + 1)
        sparse = [[0] * sz for _ in range(LOG)]
        sparse[0] = left_totals[:]
        for k in range(1, LOG):
            for i in range(sz - (1 << k) + 1):
                sparse[k][i] = max(sparse[k - 1][i], sparse[k - 1][i + (1 << (k - 1))])

        def range_max(lo: int, hi: int) -> int:
            """Max of left_totals[lo..hi] inclusive."""
            if lo > hi:
                return -1
            length = hi - lo + 1
            k = int(math.log2(length))
            return max(sparse[k][lo], sparse[k][hi - (1 << k) + 1])
    else:
        def range_max(lo: int, hi: int) -> int:
            return -1

    # Enumerate right half and combine
    best = 0

    right_states = enumerate_half(right_weights)

    for total_r, diff_r in right_states:
        # We need: |diff_r + diff_l| <= max_diff
        # => -max_diff - diff_r <= diff_l <= max_diff - diff_r
        lo_val = -max_diff - diff_r
        hi_val = max_diff - diff_r

        # Binary search in left_diffs for this range
        lo_idx = bisect_left(left_diffs, lo_val)
        hi_idx = bisect_right(left_diffs, hi_val) - 1

        if lo_idx <= hi_idx:
            best_left = range_max(lo_idx, hi_idx)
            best = max(best, total_r + best_left)

    return best


if __name__ == "__main__":
    # Test cases
    # Simple case: 2 containers, no difference allowed
    assert max_cargo([3, 3], 0) == 6  # both loaded, 3 each hold
    assert max_cargo([3, 5], 0) == 0  # can't balance with diff=0 unless skip both or load none
    # Actually [3,5] with diff=0: hold1=3,hold2=5 => diff=2 > 0. skip both => 0.
    # hold1=3,skip5 => diff=3 > 0. hold2=5,skip3 => diff=5>0. So 0 is wrong...
    # Wait: hold1=3, hold2=3 is not possible (only one container of weight 3).
    # With diff=0: no valid loading except 0. Let me reconsider.
    # Actually we CAN load a single item into hold1 with diff=|w|, so [3,5] with D=0 => 0.

    # [3,5] with D=2: hold1=5, hold2=3 => diff=2 <= 2, total=8. Yes!
    assert max_cargo([3, 5], 2) == 8

    # [1,2,3,4,5] with D=1: best partition: {1,4,5}=10 vs {2,3}=5? diff=5.
    # {5,2}=7 vs {4,3}=7 => diff=0, total=14. skip 1 => total=14.
    # Or load all: {1,3,4}=8 vs {2,5}=7 => diff=1, total=15!
    assert max_cargo([1, 2, 3, 4, 5], 1) == 15

    # Edge cases
    assert max_cargo([], 10) == 0
    assert max_cargo([100], 100) == 100  # single item in one hold, diff=100 <= 100
    assert max_cargo([100], 99) == 0     # single item, diff=100 > 99

    print("All tests passed!")
