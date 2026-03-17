# Mnemos — Workflow

## Input

The user will provide: $ARGUMENTS

This could be a problem description, a code snippet to review, or a request to refactor.

## Workflow

### If solving a new problem:

1. **ANALYZE** the problem. Identify:
   - Structural signals: What is the shape? (sorted input? graph? overlapping subproblems? pair search?)
   - Data structures likely involved (array, hashmap, heap, graph, stack, dp, etc.)
   - Constraints (input size n, space limits, time targets)

2. **CALL** `plan_algorithm` with:
   - `problem`: structural description of what needs to be solved
   - `structural_signals`: list of signals you identified, using natural language that describes the structure, e.g.:
     - "sorted input with pair satisfying arithmetic constraint"
     - "find maximum sum contiguous subarray with possible negatives"
     - "validate nested open/close delimiter matching"
     - "order tasks/items respecting dependency constraints in a DAG"
     - "count or fill connected regions in a 2D grid"
     - "find k largest/smallest elements from collection"
     - "count occurrences of each element for frequency-based decisions"
     - "shortest path in weighted graph with non-negative edges"
     - "align or compare two sequences optimally"
     - "track connected components as edges are added dynamically"
     - "merge, insert, or analyze overlapping intervals"
   - `structures`: your guess of relevant structures
   - `constraints`: e.g. `{"n": 1000000}`

3. **INTERPRET** the response:
   - `matched_rules` → primary recommendations from decision rules (use these first)
   - `consider` → ranked patterns with complexity info
   - `knowledge` → full structure details if you requested structures
   - `filtered_out` → what was eliminated by constraints and why
   - `memory` → past regressions or decisions to be aware of

4. **DECIDE** on the best pattern. Explain your reasoning.

5. **IMPLEMENT** the solution — write complete, working code. Do not stop at the recommendation.

6. **CALL** `log_decision` to record what you chose:
   - `mode`: "plan"
   - `problem`: what was solved
   - `pattern_chosen`: the pattern you used
   - `ds_chosen`: the data structure you used
   - `outcome`: "accepted"

### If reviewing existing code:

1. **READ** the code. Identify the pattern, data structures, estimate complexity.

2. **CALL** `review_complexity` with:
   - `detected_pattern`: what pattern you see
   - `detected_structures`: what DS you see
   - `detected_complexity`: your estimate
   - `constraints`: any known constraints

3. **INTERPRET**: Is it feasible? Are there better alternatives? Any past regressions?

4. If improvements needed, **CALL** `suggest_refactor` with:
   - `current_pattern`, `current_structure`, `current_complexity`
   - `target_complexity`: what you want to achieve

5. **RECOMMEND** changes with reasoning.

### If refactoring:

1. **DIAGNOSE** the current code — pattern, structure, complexity.
2. **CALL** `suggest_refactor` with current state and target.
3. **REASON** about alternatives using the knowledge returned.
4. **IMPLEMENT** the refactored solution.
5. **CALL** `log_decision` with `mode: "maintain"`.

## Always

- Call the tools — that's the whole point. Don't just solve from your own training.
- Show what the tool recommended and explain how you used its guidance.
- If the tool's recommendation conflicts with your reasoning, explain the conflict and your decision.
