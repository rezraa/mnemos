# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""
Ride-Sharing Matching: Minimize the maximum pickup distance.

Approach (recommended by Mnemos MCP):
  Pattern: binary search on answer + bipartite matching (Hopcroft-Karp)
  DS: graph (adjacency list)
  Time: O(N^2 * sqrt(N) * log(N^2)) — binary search over O(N^2) candidate
        distances, each iteration builds graph O(N^2) and runs Hopcroft-Karp
        O(E*sqrt(V)) where E <= N^2, V = 2N.
  Space: O(N^2)
"""

from __future__ import annotations
import math
from collections import deque


def _hopcroft_karp(adj: list[list[int]], n_left: int, n_right: int) -> int:
    """Return size of maximum matching in bipartite graph.

    adj[u] = list of right-side nodes that left node u connects to.
    Left nodes: 0..n_left-1, Right nodes: 0..n_right-1.
    """
    INF = float('inf')
    match_l = [-1] * n_left
    match_r = [-1] * n_right
    dist = [0] * n_left

    def bfs() -> bool:
        queue = deque()
        for u in range(n_left):
            if match_l[u] == -1:
                dist[u] = 0
                queue.append(u)
            else:
                dist[u] = INF
        found = False
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                w = match_r[v]
                if w == -1:
                    found = True
                elif dist[w] == INF:
                    dist[w] = dist[u] + 1
                    queue.append(w)
        return found

    def dfs(u: int) -> bool:
        for v in adj[u]:
            w = match_r[v]
            if w == -1 or (dist[w] == dist[u] + 1 and dfs(w)):
                match_l[u] = v
                match_r[v] = u
                return True
        dist[u] = INF
        return False

    matching = 0
    while bfs():
        for u in range(n_left):
            if match_l[u] == -1:
                if dfs(u):
                    matching += 1
    return matching


def min_max_pickup(
    drivers: list[tuple[int, int]], riders: list[tuple[int, int]]
) -> float:
    """Find 1-to-1 matching minimizing the maximum Euclidean pickup distance."""
    n = len(drivers)
    if n == 0:
        return 0.0

    # Precompute all pairwise distances
    dists = []
    dist_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        dx_base, dy_base = drivers[i]
        for j in range(n):
            rx, ry = riders[j]
            d = math.hypot(dx_base - rx, dy_base - ry)
            dist_matrix[i][j] = d
            dists.append(d)

    # Collect unique candidate thresholds and sort them
    dists.sort()
    # Remove duplicates
    candidates = []
    prev = -1.0
    for d in dists:
        if d != prev:
            candidates.append(d)
            prev = d

    # Binary search over candidate distances
    lo, hi = 0, len(candidates) - 1
    ans = candidates[-1]

    while lo <= hi:
        mid = (lo + hi) // 2
        threshold = candidates[mid]

        # Build adjacency list for this threshold
        adj = [[] for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if dist_matrix[i][j] <= threshold:
                    adj[i].append(j)

        # Check if perfect matching exists
        if _hopcroft_karp(adj, n, n) == n:
            ans = threshold
            hi = mid - 1
        else:
            lo = mid + 1

    return ans
