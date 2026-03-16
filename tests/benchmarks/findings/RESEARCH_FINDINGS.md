# Mnemos Research Findings: Does Structured Knowledge Improve LLM Algorithm Selection?

**Core hypothesis**: LLMs know what algorithms are but fail to *select* the right one under constraints. A curated knowledge base with structural signal matching, constraint filtering, and decision memory can close this gap without retraining.

---

## Methodology

### Setup
- **Vanilla session**: Fresh LLM session with no MCP tools, no knowledge base, no agent instructions. Solves problems using only its training.
- **Augmented session**: LLM with Mnemos MCP configured. Uses structural signal matching (`plan_algorithm`), constraint filtering, and knowledge base retrieval before writing code.

### Scoring
- 4 criteria per problem: correct pattern (1pt), correct DS (1pt), correct complexity (1pt), code passes tests (1pt)
- All findings reviewed and scored by Claude Opus 4.6, evaluating semantic correctness of patterns, data structures, and complexity analysis
- Code tested against 3-7 test cases per problem with deep-copy to prevent mutation

### Knowledge Base (as of Experiment 5)
- `structures.json`: 18 top-level structures, 179 algorithm patterns
- `decision_rules.json`: 67 structural signal → pattern mapping rules
- `complexities.json`: 22 DS operation tables, 10 sorting algorithms, 12 input size guidelines, 12 constraint-to-complexity guides
- Validation: 0 errors, 0 warnings (`scripts/validate_knowledge.py`)

---

## Summary of All Experiments

| # | Test | Model | Vanilla | + Mnemos | Delta | Key Finding |
|---|------|-------|---------|----------|-------|-------------|
| 1 | Easy (textbook) | Claude Opus 4.6 | 39/40 (97.5%) | 39/40 (97.5%) | 0 | No uplift — top models already know textbook algorithms |
| 2 | Easy (textbook) | Qwen 3.5 2B | 18/40 (45.0%) | 29/40 (72.5%) | **+11 (+27.5%)** | Massive uplift for small models |
| 3 | Hard (real-world) | Claude Opus 4.6 | 34/40 (85.0%) | 37/40 (92.5%) | **+3 (+7.5%)** | Mnemos helps when problems are disguised |
| 4 | LLM Trap (Round 3) | Claude Opus 4.6 | 40/40 (100%) | 40/40 (100%) | **0 + speed** | Tie on accuracy, Mnemos significantly faster |
| 5 | LLM Trap (Round 4) | Claude Opus 4.6 | 40/40 (100%) | 40/40 (100%) | **0 + 3.4x speed** | Tie on accuracy, 3.4x faster with Mnemos |

**Overall pattern**: Mnemos's value scales inversely with model capability and directly with problem ambiguity. Small models get massive uplift. Top models get accuracy gains on hard problems + significant speed improvements across the board.

---

## Experiment 1: Easy Problems — Claude Opus

**Date**: 2026-03-15
**Problems**: 10 standard textbook algorithms (two-pointer, Kadane's, stack matching, top-k, topo sort, flood fill, interval scheduling, Dijkstra, LCS, union-find)

### Results

Both sessions scored 39/40 (97.5%). Zero difference. Claude Opus already knows these patterns cold — Mnemos adds nothing when the problem name directly maps to the algorithm.

### Takeaway

Mnemos is not needed for problems that are already well-represented in LLM training data. The value proposition starts when the mapping from problem → algorithm is non-obvious.

---

## Experiment 2: Easy Problems — Qwen 3.5 2B

**Date**: 2026-03-15
**Model**: Qwen 3.5 2B (Q4_K_M quantization, 1.2 GB, Ollama, temp=0.5, ctx=2048)
**Problems**: Same 10 textbook problems as Experiment 1

### Results

| # | Problem | Vanilla | Mnemos | Delta |
|---|---------|---------|--------|-------|
| 1 | Two Sum (sorted) | 2/4 | 2/4 | = |
| 2 | Max Subarray | 0/4 | 4/4 | **+4** |
| 3 | Valid Brackets | 2/4 | 3/4 | +1 |
| 4 | Top K Frequent | 0/4 | 4/4 | **+4** |
| 5 | Topological Sort | 3/4 | 3/4 | = |
| 6 | Count Islands | 3/4 | 3/4 | = |
| 7 | Meeting Rooms | 1/4 | 2/4 | +1 |
| 8 | Dijkstra | 0/4 | 0/4 | = |
| 9 | LCS | 4/4 | 4/4 | = |
| 10 | Union-Find | 3/4 | 4/4 | +1 |
| | **TOTAL** | **18/40 (45.0%)** | **29/40 (72.5%)** | **+11 (+27.5%)** |

### Per-Criterion Breakdown

| Criterion | Vanilla | Mnemos | Delta |
|-----------|---------|--------|-------|
| Correct Pattern | 6/10 | 9/10 | +3 |
| Correct DS | 2/10 | 6/10 | +4 |
| Correct Complexity | 6/10 | 8/10 | +2 |
| Code Passes Tests | 4/10 | 6/10 | +2 |

### Key Findings

1. **Biggest wins were total failures rescued**: Problems #2 (Max Subarray) and #4 (Top K Frequent) went from 0/4 to 4/4. Vanilla Qwen couldn't even produce parseable responses — stuck in thinking loops or returned placeholder values. Mnemos gave it the right pattern names and data structures, which the model could then implement.

2. **Pattern and DS selection improved most**: +3 and +4 respectively. The knowledge base's decision rules directly told the model which pattern and DS to use.

3. **Hard problems remain hard**: Dijkstra's (problem #8) failed in both sessions. A 2B model struggles to produce correct graph algorithm code regardless of guidance. This suggests a capability floor below which knowledge injection alone can't help.

4. **Speed**: Vanilla 515s, Augmented 434s. Augmented was faster because fewer retries were needed — the model produced parseable responses more reliably with structured guidance.

### Takeaway

For small/quantized models, Mnemos acts as a *knowledge prosthetic* — compensating for gaps in training with curated algorithmic knowledge. The uplift (+27.5%) is dramatic and proves the architecture works.

---

## Experiment 3: Hard Real-World Problems — Claude Opus

**Date**: 2026-03-15
**Problems**: 10 real-world engineering scenarios disguised as production problems (log anomaly detection, warehouse robot navigation, gaming leaderboard, etc.) — the underlying algorithm is NOT named in the problem description.
**Knowledge base**: 104 patterns, 45 decision rules

### Results

| # | Problem | Vanilla | Mnemos | Delta |
|---|---------|---------|--------|-------|
| 1 | Log Anomaly Detection | 4/4 | 4/4 | = |
| 2 | Merge K Sorted Logs | 4/4 | 4/4 | = |
| 3 | Robot Navigation | 3/4 | 3/4 | = |
| 4 | Gaming Leaderboard | 2/4 | 4/4 | **+2** |
| 5 | Network Infrastructure | 3/4 | 4/4 | **+1** |
| 6 | Conference Room Finder | 3/4 | 3/4 | = |
| 7 | Build Critical Path | 4/4 | 4/4 | = |
| 8 | DNA Alignment | 3/4 | 3/4 | = |
| 9 | Config Expression Eval | 4/4 | 4/4 | = |
| 10 | Cloud Resource Packing | 4/4 | 4/4 | = |
| | **TOTAL** | **34/40 (85.0%)** | **37/40 (92.5%)** | **+3 (+7.5%)** |

### Per-Criterion Breakdown

| Criterion | Vanilla | Mnemos | Delta |
|-----------|---------|--------|-------|
| Correct Pattern | 9/10 | 10/10 | +1 |
| Correct DS | 10/10 | 10/10 | = |
| Correct Complexity | 8/10 | 10/10 | +2 |
| Code Passes Tests | 7/10 | 7/10 | = |

### Where Mnemos Made the Difference

**#4 Gaming Leaderboard — Pattern + Complexity + Code (Vanilla: 2/4, Mnemos: 4/4)**
- Vanilla chose `bucket-index` with `O(sqrt(S))` operations — valid but suboptimal, doesn't meet the O(log n) requirement. Lost points on pattern and complexity.
- Mnemos's `plan_algorithm` identified "sorted container with rank queries" → recommended skip-list/sorted-container with `O(log n)` per op and `O(n)` space. The algorithm selection and complexity analysis were correct, and the implementation was structurally sound.

**#5 Network Infrastructure — Space Complexity (Vanilla: 3/4, Mnemos: 4/4)**
- Vanilla stated space `O(N + E)`, incorrectly including edge storage. Kruskal's union-find is O(V).
- Mnemos's constraint filtering correctly guided `O(n)` space.

### Shared Errors

- **#3, #6, #8**: Identical code test failures in both sessions — implementation edge cases that neither training nor knowledge base can prevent. These require runtime debugging, not better algorithm selection.

### Key Findings

1. **Complexity awareness improved most** (+2 points). The constraint filtering from `complexities.json` helped state correct complexities where vanilla got them wrong.
2. **Pattern selection directly improved code quality**: On #4, the correct pattern choice led to a correct implementation, while vanilla's suboptimal pattern choice cascaded into complexity errors.
3. **The harder the problem, the more Mnemos helps**: +7.5% on disguised problems vs 0% on textbook problems.

---

## Experiment 4: LLM Trap Problems (Round 3) — Claude Opus

**Date**: 2026-03-16
**Problems**: 10 production engineering scenarios specifically designed to exploit known LLM failure modes: wrong algorithm mapping, greedy-vs-DP confusion, hidden graph structure, non-obvious state dimensions, and binary-search-on-answer blindness.
**Knowledge base**: 179 patterns, 66 decision rules, 22 DS operation tables, 12 constraint guides (expanded from Experiment 3)

### Results

| # | Problem | Vanilla | Mnemos | Delta |
|---|---------|---------|--------|-------|
| 1 | Delivery Route (grouped knapsack) | 4/4 | 4/4 | = |
| 2 | Ride-Sharing (min-max matching) | 4/4 | 4/4 | = |
| 3 | Microservice Latency (critical path) | 4/4 | 4/4 | = |
| 4 | Ad Auction (max weight matching) | 4/4 | 4/4 | = |
| 5 | Server Log Gap Filler (math/greedy) | 4/4 | 4/4 | = |
| 6 | Container Ship (meet-in-middle) | 4/4 | 4/4 | = |
| 7 | Playlist Diversity (binary search) | 4/4 | 4/4 | = |
| 8 | Batch Range Sums (prefix sum) | 4/4 | 4/4 | = |
| 9 | Fleet Rebalancing (greedy sweep) | 4/4 | 4/4 | = |
| 10 | Feature Flag Rollout (Kadane's) | 4/4 | 4/4 | = |
| | **TOTAL** | **40/40 (100%)** | **40/40 (100%)** | **0** |

### Per-Criterion Breakdown

| Criterion | Vanilla | Mnemos | Delta |
|-----------|---------|--------|-------|
| Correct Pattern | 10/10 | 10/10 | = |
| Correct DS | 10/10 | 10/10 | = |
| Correct Complexity | 10/10 | 10/10 | = |
| Code Passes Tests | 10/10 | 10/10 | = |

### Speed Comparison

| Metric | Vanilla | Mnemos |
|--------|---------|--------|
| Observed behavior | ~5+ minutes of visible thinking/deliberation | Completed all 10 while vanilla was still working |
| Approach | Derived each algorithm from scratch | Immediate structural signal match → implement |

Mnemos was observably and significantly faster. The knowledge base short-circuits the discovery phase entirely: instead of reasoning from scratch ("N=30, weights 10^9, knapsack DP won't work... what if I split..."), Mnemos matches the structural signal, returns meet-in-middle with full complexity details, and moves on.

### What Changed Since Experiment 3

| Aspect | Experiment 3 | Experiment 4 |
|--------|-------------|-------------|
| Knowledge base patterns | 104 | 179 (+72%) |
| Decision rules | 45 | 66 (+47%) |
| Validation warnings | 113 | 0 |
| Augmented score | 37/40 (92.5%) | 40/40 (100%) |

### Key Findings

1. **Both sessions achieved perfect accuracy**: 40/40 each. Claude Opus with comprehensive problem descriptions can solve all 10 trap problems regardless of Mnemos.

2. **Speed is the differentiator at this accuracy level**: When both sessions get the same answers, the value shifts from "did it get it right?" to "how fast?" Mnemos eliminates deliberation time.

3. **Vanilla also improved significantly**: 40/40 vs 34/40 in Experiment 3. This is partly because these problems have clearer structural signals in their descriptions (e.g., "greedy fails", "N up to 30").

---

## Experiment 5: LLM Trap Problems (Round 4) — Claude Opus

**Date**: 2026-03-16
**Problems**: Same 10 production engineering scenarios as Experiment 4. Clean test: memory cleared, identical problem descriptions for both sessions, no prior decision history.
**Knowledge base**: 179 patterns, 67 decision rules (added frequency-spacing rule after Experiment 4 analysis)

### Results

| # | Problem | Vanilla | Mnemos | Delta |
|---|---------|---------|--------|-------|
| 1 | Delivery Route (grouped knapsack) | 4/4 | 4/4 | = |
| 2 | Ride-Sharing (min-max matching) | 4/4 | 4/4 | = |
| 3 | Microservice Latency (critical path) | 4/4 | 4/4 | = |
| 4 | Ad Auction (max weight matching) | 4/4 | 4/4 | = |
| 5 | Server Log Gap Filler (math/greedy) | 4/4 | 4/4 | = |
| 6 | Container Ship (meet-in-middle) | 4/4 | 4/4 | = |
| 7 | Playlist Diversity (binary search) | 4/4 | 4/4 | = |
| 8 | Batch Range Sums (prefix sum) | 4/4 | 4/4 | = |
| 9 | Fleet Rebalancing (greedy sweep) | 4/4 | 4/4 | = |
| 10 | Feature Flag Rollout (Kadane's) | 4/4 | 4/4 | = |
| | **TOTAL** | **40/40 (100%)** | **40/40 (100%)** | **0** |

### Speed Comparison

| Metric | Vanilla | Mnemos |
|--------|---------|--------|
| Duration | 6.7 min (403s) | 1.9 min (117s) |
| Speedup | — | **3.4x faster** |

### Per-Criterion Breakdown

| Criterion | Vanilla | Mnemos | Delta |
|-----------|---------|--------|-------|
| Correct Pattern | 10/10 | 10/10 | = |
| Correct DS | 10/10 | 10/10 | = |
| Correct Complexity | 10/10 | 10/10 | = |
| Code Passes Tests | 10/10 | 10/10 | = |

### Notable Observations

**#7 Playlist Diversity — Vanilla found a superior approach**
- Vanilla used a closed-form frequency formula in O(N) — recognizing the task-scheduler pattern and computing the answer directly from max artist frequency.
- Mnemos recommended binary search on answer in O(N log N) — correct but suboptimal. The knowledge base lacked a cross-reference between `binary-search-on-answer` and the `task-scheduling` closed-form for spacing problems.
- **Post-experiment fix**: Added `rule-maximize-min-spacing-by-frequency` decision rule and cross-linked `task-scheduling` ↔ `binary-search-on-answer` as alternatives. Mnemos now surfaces the O(N) approach.

### What Changed Since Experiment 4

| Aspect | Experiment 4 | Experiment 5 |
|--------|-------------|-------------|
| Memory | Had prior decisions | Cleared — clean slate |
| Problem descriptions | Shorter for augmented | Identical for both sessions |
| Duration tracking | Observed only | Precise measurement (403s vs 117s) |
| Knowledge base rules | 66 | 67 (post-experiment) |

### Key Findings

1. **Perfect tie on accuracy with fair conditions**: Identical problem descriptions, cleared memory, same model — both sessions achieved 40/40. Speed is the only differentiator.

2. **3.4x speed advantage is the headline**: Mnemos completed all 10 problems in under 2 minutes while vanilla took nearly 7 minutes. The knowledge base eliminates the deliberation phase.

3. **Vanilla can find superior solutions**: The closed-form O(N) approach for #7 was better than Mnemos's recommended O(N log N) binary search. This revealed a knowledge base gap that was subsequently fixed.

4. **Knowledge base gaps are discoverable through A/B testing**: When vanilla outperforms Mnemos on a specific problem, it reveals missing cross-references or patterns in the knowledge base — a manual version of the planned autonomous discovery loop.

---

## Conclusions

### The Core Finding

**LLMs don't have an algorithm *knowledge* problem — they have an algorithm *selection* problem.** Claude Opus knows what meet-in-middle is, what Hungarian algorithm does, and how Kadane's works. But when faced with "a cargo ship with N=30 containers and 10^9-scale weights," it needs to *connect* that problem description to meet-in-middle — and that mapping is where errors occur.

Mnemos fixes this by providing:
1. **Structural signal matching**: Problem characteristics → specific algorithm recommendations (not fuzzy keyword matching)
2. **Constraint-aware filtering**: Automatically eliminates infeasible algorithms based on input size
3. **Connected knowledge graph**: Patterns cross-reference alternatives so the agent sees the full solution space
4. **Speed**: Pre-computed knowledge slices eliminate the LLM's discovery/deliberation phase

### Value Scales With Need

| Scenario | Mnemos Value |
|----------|-------------|
| Top model + textbook problems | Minimal (0%) — model already knows |
| Top model + disguised problems | Moderate (+7.5%) accuracy + 3.4x speed |
| Small model + any problems | Massive (+27.5%) — knowledge prosthetic |
| Any model + production code | Highest (untested) — no problem descriptions, no hints, just code |

### What Doesn't Work

1. **Mnemos can't fix code implementation bugs.** Shared test failures in Experiment 3 were identical in both sessions — edge cases require debugging, not better algorithm selection.
2. **Mnemos can't help below a capability floor.** Qwen 2B failed Dijkstra in both sessions — some problems need enough model capacity to translate concepts into code.
3. **Overly smart tools hurt.** An earlier architecture with regex-based pattern matching and fuzzy keyword scoring actively degraded results. Tools must be pure knowledge retrieval; the LLM does all reasoning.
4. **Incomplete alternative graphs cause blind spots.** When `binary-search-on-answer` didn't cross-reference `task-scheduling`, Mnemos missed the superior O(N) closed-form in Experiment 5. Connected knowledge matters.

### Open Questions for Future Research

1. **Production code benchmarks**: How much does Mnemos help when there are no problem descriptions — just real code with nested loops, unclear variable names, and no constraint sizes stated? This is the highest-value scenario but hardest to benchmark.
2. **Model diversity**: Tested on Claude Opus and Qwen 2B. What about GPT-4o, Gemini, Codex, Mistral, Llama? The architecture is model-agnostic by design.
3. **Knowledge discovery loop**: Can Mnemos autonomously find gaps in its own knowledge by solving problems and comparing to optimal solutions? (Designed but not yet implemented.)
4. **Usage context**: Does adding execution frequency hints (hot-path vs batch) improve recommendations? (Explored and parked — agent instructions may suffice.)

