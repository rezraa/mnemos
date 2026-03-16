# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""Server Log Gap Finder.

Given sorted timestamps, find the minimum number of synthetic timestamps
to insert so that no consecutive gap exceeds K.

Pattern: Linear Scan (single pass over sorted array)
DS: Array
Time: O(n)
Space: O(1)
"""

import math


def min_insertions(timestamps: list[int], k: int) -> int:
    """Return the minimum synthetic timestamps to insert so no gap > k.

    For each consecutive pair, the number of insertions needed is
    ceil(gap / k) - 1, which equals (gap - 1) // k when gap > k,
    and 0 otherwise.

    Args:
        timestamps: Sorted list of integer timestamps.
        k: Maximum allowed gap between consecutive timestamps.

    Returns:
        Total number of synthetic timestamps to insert.
    """
    if len(timestamps) <= 1 or k <= 0:
        return 0

    total = 0
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        if gap > k:
            # ceil(gap / k) - 1 == (gap - 1) // k  when gap > 0
            total += (gap - 1) // k
    return total


if __name__ == "__main__":
    # Quick test cases
    assert min_insertions([1, 5], 2) == 1       # gap=4, ceil(4/2)-1 = 1
    assert min_insertions([1, 10], 3) == 2       # gap=9, ceil(9/3)-1 = 2
    assert min_insertions([1, 2, 3], 1) == 0     # all gaps = 1
    assert min_insertions([0, 100], 10) == 9     # gap=100, ceil(100/10)-1 = 9
    assert min_insertions([1, 6, 12], 3) == 2    # gap=5: 1, gap=6: 1 -> total 2
    assert min_insertions([], 5) == 0
    assert min_insertions([42], 5) == 0
    print("All tests passed.")
