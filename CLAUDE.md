# Mnemos

Mnemos is an AI agent providing algorithm and data structure recommendations grounded in structural reasoning.

## Mnemos Agent

Use the `/mnemos` slash command to invoke the Mnemos agent. It handles the full workflow: analyzing problems, calling MCP tools, interpreting results, and implementing solutions.

```
/mnemos <problem description or code to review>
```

Examples:
- `/mnemos Given a sorted array and a target sum, find two numbers that add up to the target. Array has up to 10^6 elements.`
- `/mnemos Review the complexity of this sorting function in src/sort.py`
- `/mnemos Refactor the nested loop search in src/search.py to be faster than O(n^2)`

## How It Works

**You do the reasoning. The tools give you curated CS knowledge + empirical memory.**

The agent (LLM) reads code, identifies structural patterns, and makes decisions. The MCP tools match the agent's analysis against a curated knowledge base of 40+ algorithmic patterns across 12 data structures and 37 decision rules.

## MCP Tools Available

- `plan_algorithm` — Match structural signals against decision rules, get pattern recommendations
- `review_complexity` — Check feasibility of detected complexity against constraints
- `suggest_refactor` — Get alternatives filtered by target complexity
- `log_decision` — Record algorithmic decisions to memory
- `bootstrap_context` — Store project codebase context

## Running the Server

```bash
cd /Users/rezamalik/Repos/mnemos
.venv/bin/python -m mnemos.server
```

Or via the `mnemos` command if installed.
