<p align="center">
  <img src="graphics/mnemos4.png" alt="Mnemos: Algorithmic Reasoning Agent for LLMs" width="100%">
</p>

<h1 align="center">Mnemos</h1>

<p align="center">
  <strong>Algorithmic Reasoning Agent for LLMs</strong><br>
  An AI agent that closes the algorithm <em>selection</em> gap, because LLMs know what algorithms are, they just pick the wrong one.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white" alt="Python"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-Compatible-8A2BE2.svg" alt="MCP"></a>
  <a href="https://ko-fi.com/rezraa"><img src="https://img.shields.io/badge/Ko--fi-Support-ff5e5b.svg?logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
</p>

---

## The Problem

LLMs don't have an algorithm **knowledge** problem, they have an algorithm **selection** problem. Claude Opus knows what meet-in-middle is. But when faced with *"a cargo ship with N=30 containers and 10^9-scale weights"*, it needs to **connect** that problem to meet-in-middle, and that mapping is where errors occur.

## The Solution

Mnemos is an **AI agent** that provides algorithmic reasoning backed by a curated knowledge base. It uses [MCP](https://modelcontextprotocol.io) tools as its hands to perform **structural signal matching**, complexity analysis, constraint filtering, and alternative lookups, while the agent itself handles all reasoning. Instead of fuzzy keyword matching or regex-based analysis, it lets the LLM identify structural signals and returns precise algorithm recommendations with the full solution space.

Named after **Mnemosyne**, titan goddess of memory.

## Research Results

We ran controlled A/B experiments comparing vanilla LLM sessions against Mnemos-augmented sessions. All findings reviewed and scored by Claude Opus 4.6.

| Test | Model | Vanilla | + Mnemos | Delta |
|------|-------|---------|----------|-------|
| Easy (textbook) | Claude Opus 4.6 | 39/40 (97.5%) | 39/40 (97.5%) | 0, model already knows |
| Easy (textbook) | Qwen 3.5 2B | 18/40 (45.0%) | 29/40 (72.5%) | **+27.5%**, massive uplift |
| Hard (real-world) | Claude Opus 4.6 | 34/40 (85.0%) | 37/40 (92.5%) | **+7.5%**, helps on disguised problems |
| LLM Traps (Round 3) | Claude Opus 4.6 | 40/40 (100%) | 40/40 (100%) | Tie + speed advantage |
| LLM Traps (Round 4) | Claude Opus 4.6 | 40/40 (100%) | 40/40 (100%) | Tie + **3.4x faster** |

**Key findings:**
- **Small models get massive uplift**: +27.5% for a 2B parameter model
- **Top models get speed**: 3.4x faster on hard problems (1.9 min vs 6.7 min)
- **Disguised problems benefit most**: +7.5% when algorithms aren't named in the problem
- **Value scales inversely with model capability** and directly with problem ambiguity

Full findings: [`tests/benchmarks/findings/RESEARCH_FINDINGS.md`](tests/benchmarks/findings/RESEARCH_FINDINGS.md)

## Architecture

```
Claude Code (top-level LLM) → calls agents
  └─ Mnemos Agent (reasoning via CLAUDE.md instructions)
       └─ Mnemos MCP Tools (pure knowledge retrieval)
            └─ JSON Knowledge Base (curated algorithms + decision rules)
```

**Tools do structural comparisons** against curated JSON knowledge. **The agent does all reasoning.**

### MCP Tools

| Tool | Purpose |
|------|---------|
| `plan_algorithm` | Structural signal matching → pattern recommendations with constraint filtering |
| `review_complexity` | Feasibility check against knowledge base complexities |
| `suggest_refactor` | Alternative lookup filtered by target complexity |
| `log_decision` | Record decisions for regression tracking |
| `bootstrap_context` | Initialize project-level codebase context |

### Knowledge Base

| Resource | Contents |
|----------|----------|
| `structures.json` | 18 data structures, 179 algorithm patterns with cross-referenced alternatives |
| `decision_rules.json` | 67 structural signal → pattern mapping rules |
| `complexities.json` | 22 DS operation tables, 10 sorting algorithms, 12 input size guidelines |

All patterns form a **connected knowledge graph**. Alternatives are bidirectionally linked so the agent always sees the full solution space. Validated with 0 errors, 0 warnings.

## Quick Start

### Install

```bash
git clone https://github.com/rezraa/mnemos.git
cd mnemos
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Run

```bash
# macOS / Linux
./server.sh                    # Start both MCP server and dashboard
./server.sh --mcp-only         # MCP server only
./server.sh --dashboard-only   # Dashboard only

# Windows
server.bat                     # Start both (separate windows)
server.bat --mcp-only          # MCP server only
server.bat --dashboard-only    # Dashboard only
```

### Configure with Claude Code

Create a `.mcp.json` file in the repo root (it's gitignored):

```json
{
  "mcpServers": {
    "mnemos": {
      "command": "/path/to/mnemos/.venv/bin/python",
      "args": ["-m", "mnemos.server"],
      "cwd": "/path/to/mnemos"
    }
  }
}
```

Replace `/path/to/mnemos` with your actual clone path. Claude Code will automatically detect this file when working in the repo.

### Validate Knowledge Base

```bash
python scripts/validate_knowledge.py
```

## How It Works

1. **Agent reads the problem**: understands code/problem in any language (the LLM's job)
2. **Agent identifies structural signals**: e.g., "maximize minimum spacing", "N=30 with large weights"
3. **Agent calls `plan_algorithm`**: tool matches signals against `decision_rules.json`, retrieves knowledge slice from `structures.json`, filters by constraints using `complexities.json`
4. **Tool returns structured knowledge**: matched rules, recommended patterns, alternatives, filtered-out patterns with reasons
5. **Agent reasons and implements**: picks the best pattern from the knowledge slice, writes the code

The tool never sees code. The agent never memorizes algorithm databases. Each does what it's best at.

## Dashboard

Start the dashboard with `./server.sh --dashboard-only` (or `server.bat --dashboard-only` on Windows) and open `http://localhost:8420`.

- **Live activity feed**: real-time stream of MCP tool calls as the agent works
- **Decision history**: every `log_decision` call recorded with pattern, structure, and reasoning
- **Regression tracking**: flags when the agent revisits a past decision with a different outcome
- **Knowledge base stats**: pattern count, rule count, alternative coverage at a glance

## Project Structure

```
mnemos/
├── src/mnemos/
│   ├── server.py          # MCP server entry point
│   ├── tools/             # MCP tool implementations
│   │   ├── plan_algorithm.py
│   │   ├── review_complexity.py
│   │   ├── suggest_refactor.py
│   │   ├── log_decision.py
│   │   └── bootstrap_context.py
│   ├── knowledge/         # Curated JSON knowledge base
│   │   ├── structures.json
│   │   ├── decision_rules.json
│   │   └── complexities.json
│   ├── memory/            # Decision memory + regression tracking
│   └── dashboard/         # Real-time monitoring UI
├── scripts/               # Validation and maintenance
├── tests/
│   └── benchmarks/        # A/B test infrastructure and findings
├── server.sh              # Start script (MCP + dashboard)
└── PLAN.md                # Architecture and roadmap
```

## Support

If Mnemos is useful to your work, consider [buying me a coffee](https://ko-fi.com/rezraa).

## Author

**Reza Malik** | [GitHub](https://github.com/rezraa) · [Ko-fi](https://ko-fi.com/rezraa)

## License

Copyright (c) 2026 Reza Malik. [Apache 2.0](LICENSE)
