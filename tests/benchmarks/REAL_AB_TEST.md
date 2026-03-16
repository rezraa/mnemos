# Real-World A/B Test: Vanilla Claude vs Claude + Mnemos Agent — Round 3

## How This Works

10 **production engineering problems** designed to exploit known LLM failure modes: wrong algorithm mapping, greedy-vs-DP confusion, hidden graph structure, non-obvious state dimensions, and binary-search-on-answer blindness. Two sessions solve them independently.

- **Session A (Vanilla)**: Fresh Claude Code, no MCP, no Mnemos.
- **Session B (Augmented)**: Claude Code from mnemos/ with Mnemos MCP + `/mnemos` agent.

---

## Step 1: Run the Vanilla Session

Open a **new Claude Code session** from a directory with NO Mnemos configured.

Paste this prompt:

---

### Prompt for Vanilla Session

```
IMPORTANT: Record the current time at the START before solving anything, and again at the END after writing the JSON. Include both timestamps and the total duration in seconds.

I need you to solve 10 extremely hard real-world engineering problems. These are production scenarios — not textbook exercises. For each:
1. Read carefully — the optimal approach is NOT obvious
2. Choose the best algorithm and data structure for the given scale
3. Write a working Python solution (use only stdlib — no pip packages)
4. State pattern, DS, and complexity

Write ALL results to: /Users/rezamalik/Repos/mnemos/tests/benchmarks/results/vanilla_round3.json

JSON format:
{
  "session": "vanilla",
  "start_time": "<ISO timestamp when you started>",
  "timestamp": "<ISO timestamp when you finished>",
  "duration_seconds": <total seconds from start to finish>,
  "results": [
    {
      "id": 1,
      "pattern_used": "<algorithm pattern name>",
      "ds_used": "<primary data structure>",
      "time_complexity": "<e.g. O(n)>",
      "space_complexity": "<e.g. O(n)>",
      "code": "<complete Python function as string>",
      "explanation": "<1-2 sentences>"
    },
    ...
  ]
}

PROBLEM 1 — Delivery Route Optimizer:
A delivery company has N packages to deliver. Each package has a weight and a delivery fee. The truck has a weight capacity W. You want to maximize total delivery fees. HOWEVER, packages come in bundles — if you take any package from a bundle, you get a 20% bonus on all fees in that bundle but you must take ALL packages in that bundle. Individual (non-bundled) packages can be taken freely. Given packages as (weight, fee, bundle_id) where bundle_id=0 means no bundle, maximize total fees within weight capacity. N up to 1000, W up to 10000.
Function signature: def max_delivery_fee(packages: list[tuple[int, int, int]], capacity: int) -> int

PROBLEM 2 — Ride-Sharing Matching:
A ride-sharing platform has N drivers and N riders. Each driver has a location (x, y) and each rider has a pickup location (x, y). Assign each rider to exactly one driver (1-to-1 matching) to minimize the MAXIMUM distance any rider has to wait (i.e., minimize the longest pickup distance across all pairs). Return the minimized maximum distance. N up to 1000. A greedy nearest-driver approach does NOT give optimal results.
Function signature: def min_max_pickup(drivers: list[tuple[int, int]], riders: list[tuple[int, int]]) -> float

PROBLEM 3 — Microservice Call Chain:
Your distributed system has N microservices. Service calls form a DAG where each service has a processing time. Some services call multiple downstream services IN PARALLEL (all calls start at the same time, parent waits for the slowest child). Given the DAG and processing times, find the minimum total latency from the entry service (node 0) to completion of ALL services. This is NOT just the longest path — you must account for parallel execution. N up to 10000, edges up to 50000.
Function signature: def min_latency(n: int, times: list[int], calls: list[tuple[int, int]]) -> int

PROBLEM 4 — Ad Auction Revenue:
An ad platform runs auctions for N ad slots. Each advertiser bids on specific slots with different bid amounts. Each advertiser can win at most one slot, and each slot can have at most one winner. Maximize total revenue. Advertisers up to 500, slots up to 500, total bids up to 10000. A greedy "highest bid first" approach fails because it can block higher total revenue.
Function signature: def max_revenue(n_slots: int, bids: list[tuple[int, int, int]]) -> int
(bids are (advertiser_id, slot_id, amount))

PROBLEM 5 — Server Log Gap Finder:
You have a sorted stream of N server timestamps (integers). Find the minimum number of "synthetic" timestamps you need to insert so that no two consecutive timestamps are more than K apart. The catch: inserted timestamps also count as consecutive pairs with each other. Essentially, for each gap > K, you need ceil(gap/K) - 1 insertions. N up to 10^6, timestamps up to 10^18.
Function signature: def min_insertions(timestamps: list[int], k: int) -> int

PROBLEM 6 — Container Ship Loading:
A cargo ship has N containers to load. Each container has a weight. The ship has two holds (left and right) and needs to stay balanced — the weight difference between holds must not exceed D. Maximize the total weight loaded. You can choose which containers to load and into which hold. N up to 30, weights up to 10^9. A greedy approach fails; this requires careful subset enumeration.
Function signature: def max_cargo(weights: list[int], max_diff: int) -> int

PROBLEM 7 — Playlist Shuffle Distance:
A music service wants to shuffle a playlist of N songs. The "diversity score" of a shuffle is the minimum distance (in positions) between any two songs by the same artist. Maximize the diversity score. Given N songs with artist labels, return the maximum achievable minimum distance. N up to 10^5. The answer can be binary searched: "can we achieve minimum distance D?" is a feasibility check.
Function signature: def max_diversity(songs: list[int]) -> int
(songs[i] is the artist ID of song i)

PROBLEM 8 — Database Query Optimizer:
A database processes N range queries on a sorted array of M elements. Each query asks for the sum of elements in range [L, R]. The queries are known in advance. Preprocess the array so that each query is answered in O(1). Then return all answers. N up to 10^5 queries, M up to 10^6 elements. Building a segment tree is overkill — there's a simpler O(M) preprocessing approach.
Function signature: def batch_range_sums(arr: list[int], queries: list[tuple[int, int]]) -> list[int]

PROBLEM 9 — Fleet Rebalancing:
A bike-sharing system has N stations, each with a current count and a target count of bikes. You have one truck that starts at station 0 and can carry unlimited bikes. At each station, you can load or unload any number of bikes. The truck must visit stations to rebalance them. Stations are arranged in a line (positions 0 to N-1). The truck travels 1 unit per station. Find the minimum total distance the truck must travel to rebalance all stations, starting and ending at station 0. N up to 10^5.
Function signature: def min_rebalance_distance(current: list[int], target: list[int]) -> int

PROBLEM 10 — Feature Flag Rollout:
You're rolling out a feature to users. You have N user segments, each with a size and an expected revenue impact (can be negative — some segments may lose revenue). You must roll out to segments in order (segment 0 first, then 1, etc.) and once you start, you roll out to consecutive segments. You can choose WHERE to start and where to stop. Maximize total revenue impact. This is finding the maximum sum contiguous subarray — but with a twist: if the max is negative, you can choose to roll out to nobody (revenue = 0). N up to 10^6, values from -10^9 to 10^9.
Function signature: def max_rollout_revenue(segments: list[int]) -> int

After solving all 10, write the results JSON file.
```

---

## Step 2: Run the Augmented Session (Mnemos Agent)

Open a **new Claude Code session** from **`mnemos/`** with Mnemos MCP configured.

Paste this prompt:

---

### Prompt for Augmented Session

```
IMPORTANT: Record the current time at the START before solving anything, and again at the END after writing the JSON. Include both timestamps and the total duration in seconds.

I need you to solve 10 extremely hard real-world engineering problems. For EACH problem, invoke /mnemos with the problem description. The agent will call Mnemos MCP tools for algorithm recommendations and then implement the solution.

CRITICAL: Launch ALL 10 /mnemos agents in parallel — do NOT wait for one to finish before starting the next. Spawn all 10 at once and wait for all to return, then collect the results.

After all 10 are solved, collect the results and write to:
/Users/rezamalik/Repos/mnemos/tests/benchmarks/results/augmented_round3.json

JSON format:
{
  "session": "augmented",
  "start_time": "<ISO timestamp when you started>",
  "timestamp": "<ISO timestamp when you finished>",
  "duration_seconds": <total seconds from start to finish>,
  "results": [
    {
      "id": 1,
      "pattern_used": "<pattern recommended by mnemos>",
      "ds_used": "<DS recommended by mnemos>",
      "time_complexity": "<e.g. O(n)>",
      "space_complexity": "<e.g. O(n)>",
      "code": "<complete Python function as string>",
      "explanation": "<what mnemos recommended and how you used it>"
    },
    ...
  ]
}

For each problem, run: /mnemos <problem description>

PROBLEM 1 — Delivery Route Optimizer:
A delivery company has N packages to deliver. Each package has a weight and a delivery fee. The truck has a weight capacity W. You want to maximize total delivery fees. HOWEVER, packages come in bundles — if you take any package from a bundle, you get a 20% bonus on all fees in that bundle but you must take ALL packages in that bundle. Individual (non-bundled) packages can be taken freely. Given packages as (weight, fee, bundle_id) where bundle_id=0 means no bundle, maximize total fees within weight capacity. N up to 1000, W up to 10000.
Function signature: def max_delivery_fee(packages: list[tuple[int, int, int]], capacity: int) -> int

PROBLEM 2 — Ride-Sharing Matching:
A ride-sharing platform has N drivers and N riders. Each driver has a location (x, y) and each rider has a pickup location (x, y). Assign each rider to exactly one driver (1-to-1 matching) to minimize the MAXIMUM distance any rider has to wait (i.e., minimize the longest pickup distance across all pairs). Return the minimized maximum distance. N up to 1000. A greedy nearest-driver approach does NOT give optimal results.
Function signature: def min_max_pickup(drivers: list[tuple[int, int]], riders: list[tuple[int, int]]) -> float

PROBLEM 3 — Microservice Call Chain:
Your distributed system has N microservices. Service calls form a DAG where each service has a processing time. Some services call multiple downstream services IN PARALLEL (all calls start at the same time, parent waits for the slowest child). Given the DAG and processing times, find the minimum total latency from the entry service (node 0) to completion of ALL services. This is NOT just the longest path — you must account for parallel execution. N up to 10000, edges up to 50000.
Function signature: def min_latency(n: int, times: list[int], calls: list[tuple[int, int]]) -> int

PROBLEM 4 — Ad Auction Revenue:
An ad platform runs auctions for N ad slots. Each advertiser bids on specific slots with different bid amounts. Each advertiser can win at most one slot, and each slot can have at most one winner. Maximize total revenue. Advertisers up to 500, slots up to 500, total bids up to 10000. A greedy "highest bid first" approach fails because it can block higher total revenue.
Function signature: def max_revenue(n_slots: int, bids: list[tuple[int, int, int]]) -> int
(bids are (advertiser_id, slot_id, amount))

PROBLEM 5 — Server Log Gap Finder:
You have a sorted stream of N server timestamps (integers). Find the minimum number of "synthetic" timestamps you need to insert so that no two consecutive timestamps are more than K apart. The catch: inserted timestamps also count as consecutive pairs with each other. Essentially, for each gap > K, you need ceil(gap/K) - 1 insertions. N up to 10^6, timestamps up to 10^18.
Function signature: def min_insertions(timestamps: list[int], k: int) -> int

PROBLEM 6 — Container Ship Loading:
A cargo ship has N containers to load. Each container has a weight. The ship has two holds (left and right) and needs to stay balanced — the weight difference between holds must not exceed D. Maximize the total weight loaded. You can choose which containers to load and into which hold. N up to 30, weights up to 10^9. A greedy approach fails; this requires careful subset enumeration.
Function signature: def max_cargo(weights: list[int], max_diff: int) -> int

PROBLEM 7 — Playlist Shuffle Distance:
A music service wants to shuffle a playlist of N songs. The "diversity score" of a shuffle is the minimum distance (in positions) between any two songs by the same artist. Maximize the diversity score. Given N songs with artist labels, return the maximum achievable minimum distance. N up to 10^5. The answer can be binary searched: "can we achieve minimum distance D?" is a feasibility check.
Function signature: def max_diversity(songs: list[int]) -> int
(songs[i] is the artist ID of song i)

PROBLEM 8 — Database Query Optimizer:
A database processes N range queries on a sorted array of M elements. Each query asks for the sum of elements in range [L, R]. The queries are known in advance. Preprocess the array so that each query is answered in O(1). Then return all answers. N up to 10^5 queries, M up to 10^6 elements. Building a segment tree is overkill — there's a simpler O(M) preprocessing approach.
Function signature: def batch_range_sums(arr: list[int], queries: list[tuple[int, int]]) -> list[int]

PROBLEM 9 — Fleet Rebalancing:
A bike-sharing system has N stations, each with a current count and a target count of bikes. You have one truck that starts at station 0 and can carry unlimited bikes. At each station, you can load or unload any number of bikes. The truck must visit stations to rebalance them. Stations are arranged in a line (positions 0 to N-1). The truck travels 1 unit per station. Find the minimum total distance the truck must travel to rebalance all stations, starting and ending at station 0. N up to 10^5.
Function signature: def min_rebalance_distance(current: list[int], target: list[int]) -> int

PROBLEM 10 — Feature Flag Rollout:
You're rolling out a feature to users. You have N user segments, each with a size and an expected revenue impact (can be negative — some segments may lose revenue). You must roll out to segments in order (segment 0 first, then 1, etc.) and once you start, you roll out to consecutive segments. You can choose WHERE to start and where to stop. Maximize total revenue impact. This is finding the maximum sum contiguous subarray — but with a twist: if the max is negative, you can choose to roll out to nobody (revenue = 0). N up to 10^6, values from -10^9 to 10^9.
Function signature: def max_rollout_revenue(segments: list[int]) -> int

For each problem, run /mnemos with the full problem description — it will recommend the approach and implement the code. After all 10, collect the results into the JSON file.
```

---

## Step 3: Score Both Sessions

Come back to the scoring session and ask to score the results.

---

## Scoring

4 criteria per problem (max 40 total):
1. **Correct algorithm pattern**
2. **Correct data structure**
3. **Correct complexity**
4. **Code correctness** (test cases)

---

## Ground Truth

| # | Problem | Best Pattern | Best DS | Time | Space | LLM Trap |
|---|---------|-------------|---------|------|-------|----------|
| 1 | Delivery Route (grouped knapsack) | Grouped/bundled knapsack DP | DP array | O(N*W) | O(W) | Looks like plain 0/1 knapsack but bundles make items coupled — must take all-or-nothing per bundle group |
| 2 | Ride-Sharing (min-max matching) | Binary search on answer + bipartite matching check | Graph + BFS/DFS | O(N^3 log D) or O(N^2.5 log N) | O(N^2) | Looks like greedy assignment but need binary search on distance + bipartite feasibility |
| 3 | Microservice Latency (critical path) | Topological sort + longest path DP (critical path) | Graph + DP | O(V+E) | O(V+E) | Parallel execution means LONGEST path, not shortest — easy to confuse |
| 4 | Ad Auction (max weight matching) | Hungarian algorithm or max-weight bipartite matching | Graph + matrix | O(N^3) | O(N^2) | Looks like greedy assignment but it's bipartite matching — greedy blocks better global assignments |
| 5 | Log Gap Filler (math/greedy) | Simple iteration with math | Array | O(N) | O(1) | Looks like it needs DP or binary search but it's just ceiling division per gap |
| 6 | Container Ship (meet-in-middle) | Meet in the middle subset enumeration | Sorted arrays + two pointer | O(3^(N/2) * N) | O(3^(N/2)) | Looks like knapsack but N=30 with 10^9 weights makes DP infeasible — need meet-in-middle. 3 choices per item: skip, left hold, right hold |
| 7 | Playlist Diversity (binary search + greedy check) | Binary search on answer + greedy feasibility | Array + counter | O(N log N) | O(N) | Looks like a scheduling problem but it's binary search on the answer space |
| 8 | Batch Range Sums (prefix sum) | Prefix sum array | Array | O(M + N) | O(M) | Might overthink with segment tree — prefix sum is O(M) preprocess on the array, O(1) per query |
| 9 | Fleet Rebalancing (greedy sweep) | Greedy sweep tracking surplus/deficit | Array | O(N) | O(1) | Looks like it needs shortest path but truck must visit all stations anyway — just sweep left to right tracking what to carry |
| 10 | Feature Flag Rollout (Kadane's) | Kadane's algorithm (max subarray) | Array | O(N) | O(1) | Disguised max contiguous subarray — easy if recognized, but production framing can mislead |
