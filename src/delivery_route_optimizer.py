# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""
Delivery Route Optimizer — Grouped 0/1 Knapsack

Pattern: knapsack-dp (0/1 knapsack with grouped items)
DS: 1D DP array + HashMap for grouping bundles
Time:  O(M * W) where M = number of items after consolidation, W = capacity
Space: O(W) using 1D DP optimization

Approach:
1. Use a hashmap to group packages by bundle_id.
2. Consolidate each bundle into a single "super-item" with combined weight
   and total fee * 1.2 (20% bonus).
3. Individual packages (bundle_id=0) become standalone items.
4. Run standard 0/1 knapsack on all items using a 1D DP table.
"""

from collections import defaultdict


def max_delivery_fee(packages: list[tuple[int, int, int]], capacity: int) -> int:
    """
    Maximize total delivery fees within truck weight capacity.

    Args:
        packages: List of (weight, fee, bundle_id) tuples.
                  bundle_id=0 means individual package.
                  Non-zero bundle_id means all packages in that bundle
                  must be taken together for a 20% fee bonus.
        capacity: Maximum weight the truck can carry.

    Returns:
        Maximum total fee achievable (integer, rounded down).
    """
    # Step 1: Group packages by bundle_id using a hashmap
    bundles: dict[int, list[tuple[int, int]]] = defaultdict(list)
    individual_items: list[tuple[int, int]] = []

    for weight, fee, bundle_id in packages:
        if bundle_id == 0:
            individual_items.append((weight, fee))
        else:
            bundles[bundle_id].append((weight, fee))

    # Step 2: Build consolidated item list
    # Each item is (total_weight, total_fee) — ready for 0/1 knapsack
    items: list[tuple[int, int]] = list(individual_items)

    for bundle_id, bundle_packages in bundles.items():
        total_weight = sum(w for w, f in bundle_packages)
        total_fee = sum(f for w, f in bundle_packages)
        # 20% bonus on bundle fee, use int() to floor
        bonus_fee = int(total_fee * 1.2)
        items.append((total_weight, bonus_fee))

    # Step 3: 0/1 Knapsack with 1D DP
    # dp[w] = max fee achievable with weight capacity w
    dp = [0] * (capacity + 1)

    for weight, fee in items:
        if weight > capacity:
            continue
        # Traverse from right to left to ensure each item is used at most once
        for w in range(capacity, weight - 1, -1):
            dp[w] = max(dp[w], dp[w - weight] + fee)

    return dp[capacity]


if __name__ == "__main__":
    # Example test
    packages = [
        (10, 100, 0),   # individual
        (20, 150, 1),   # bundle 1
        (15, 120, 1),   # bundle 1
        (25, 200, 0),   # individual
        (5, 50, 2),     # bundle 2
        (10, 80, 2),    # bundle 2
        (30, 300, 0),   # individual
    ]
    capacity = 60

    result = max_delivery_fee(packages, capacity)
    print(f"Max delivery fee: {result}")

    # Bundle 1: weight=35, fee=int(270*1.2)=324
    # Bundle 2: weight=15, fee=int(130*1.2)=156
    # Individual: (10,100), (25,200), (30,300)
    # Best within 60: e.g. (30,300) + (25,200) + (5+10, 156) => 30+25=55, need 15 for bundle2 => 55+15=70 > 60
    #   (30,300) + (25,200) = 55 weight, 500 fee, 5 capacity left => nothing else fits
    #   (30,300) + (10,100) + (15, bundle2=156) = 55 weight, 556 fee
    #   etc.
    print("Expected: best combination within capacity 60")
