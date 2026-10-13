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

2. **RECOGNIZE, then CALL.** Retrieval is driven by the signal index — the one proven problem-language → pattern path.
   - **CALL** `get_signal_index` — it returns the compact nested container `{pattern_signals: {pattern_id: {signal_id: signal_text}}}` (one named group per corpus; Mnemos has one pattern corpus, so read `pattern_signals`). Patterns and their signals come in sorted id order; a signal owned by several patterns appears under each of them.
   - **RECOGNIZE** which of the problem's structural signals match signal texts in that group — collect their `signal_id`s (e.g. a problem with a sorted input and a pair meeting a sum target matches the signal text "sorted input with pair satisfying arithmetic constraint"). Recognize by meaning, not by keyword; a pattern id key tells you which pattern the signal routes to.
   - **CALL** `plan_algorithm` with:
     - `problem`: structural description of what needs to be solved (context only — retrieval is driven by the ids)
     - `matched_signal_ids`: the `signal_id`s you recognized
     - `constraints`: e.g. `{"n": 1000000, "input_order": "sorted"}` — `n`/`input_size` exclude complexity-infeasible patterns; the problem's traits (`updates`: static|dynamic, `arrival`: batch|streaming, `input_order`: sorted|unsorted, `query_shape`: point|range_or_order|prefix, `exactness`: exact|approximate, `value_sign`: non_negative|may_be_negative, `graph_direction`: directed|undirected, `graph_weighting`: unweighted|zero_one|weighted) reorder candidates by their own facets — state only traits the problem actually states

3. **INTERPRET** the response:
   - `retrieval_state` → read first: `hit`, `low_confidence` (best candidate below the confidence floor — weigh with care), `no_match` or `dangling` (both abstain: `recommendations` is empty)
   - `recommendations` → THE answer: ranked `{rank, pattern_id, pattern_name, structure_id, fit, retrieval, gated}`; `fit` is the pattern's own `complexity` / `use_when` / `avoid_when` / `constraints`, `retrieval` its signal votes plus `use_when_fit` (how many of its own use-facets your traits satisfy); `gated: true` means its own avoid_when names one of your traits, so it is ranked below the rest
   - `unmatched` → ids you passed that the index does not know — you recognized them wrong; re-read `get_signal_index`
   - `dangling` → pattern ids referenced by your signals that do not resolve to a corpus pattern
   - `filtered_out` → `{pattern_id, pattern_name, complexity, reason}` excluded as infeasible for your constraints
   - `memory` → `regressions` on recommended (pattern, ds) pairs; with a `project_id`, `past_decisions` / `last_pattern`
   - `context` → the project's codebase context (only with a `project_id`)

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
   - `matched_signal_ids`: `signal_id`s recognized against `get_signal_index` (as in "solving" step 2) — these drive the retrieval of better alternatives
   - `constraints`: any known constraints

3. **INTERPRET**:
   - `feasibility` → `{is_feasible, reason}` for YOUR detected complexity against the constraints (independent of retrieval)
   - `alternatives` → feasible candidates `{rank, pattern_id, pattern_name, structure_id, fit, retrieval}`; those strictly faster than your detected complexity carry `improvement` (`"<detected> -> <theirs>"`)
   - `retrieval_state` / `unmatched` / `dangling` → as in "solving" step 3; `no_match`/`dangling` leave `alternatives` empty while `feasibility`, `structure_info` and `memory` still stand
   - `filtered_out` → candidates excluded as infeasible, with `reason`
   - `structure_info` → per detected structure id, `{operations, pattern_count}`
   - `memory` → `regressions` recorded for the detected pattern; `context` → project context (with a `project_id`)

4. If improvements needed, **CALL** `suggest_refactor` with:
   - `current_pattern`: the corpus `pattern_id` (retrieval is seeded from that pattern's own signals — an unknown id abstains), `current_structure`, `current_complexity`
   - `target_complexity`: what you want to achieve
   - **INTERPRET**: `suggestions` holds ONLY candidates strictly faster than `current_complexity`, each with `fit`, `retrieval` and `improvement`; `filtered_out` holds those exceeding the target or the size guideline; `memory` carries `regressions_on_suggestions` and, with a `project_id`, `past_corrections`; `retrieval_state` / `unmatched` / `dangling` as above

5. **RECOMMEND** changes with reasoning.

### If refactoring:

1. **DIAGNOSE** the current code — pattern, structure, complexity.
2. **CALL** `suggest_refactor` with current state and target.
3. **REASON** over the returned `suggestions` (read as in "reviewing" step 4).
4. **IMPLEMENT** the refactored solution.
5. **CALL** `log_decision` with `mode: "maintain"`.

## Always

- Call the tools — that's the whole point. Don't just solve from your own training.
- Show what the tool recommended and explain how you used its guidance.
- If the tool's recommendation conflicts with your reasoning, explain the conflict and your decision.
