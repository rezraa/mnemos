# Contributing to Mnemos

Created by **Reza Malik**. Thanks for your interest in contributing.

## Contributor License Agreement

By submitting a pull request you agree to the [Contributor License Agreement](CLA.md). In short:

- Your contribution is your original work (or you have the right to submit it)
- Your contribution is licensed under [Apache 2.0](LICENSE), the same license as the project
- You grant the project maintainer a non-exclusive, irrevocable, worldwide license to use, modify, and redistribute your contribution under any license, including proprietary licenses

## What We're Looking For

We especially welcome:

- **Knowledge base additions** — new algorithm patterns, decision rules, or complexity entries (must pass `scripts/validate_knowledge.py`)
- **Bug fixes** and performance improvements
- **A/B test problem sets** — new benchmark problems for testing Mnemos's effectiveness
- **Documentation** improvements

For large feature work, **open an issue first** to discuss before investing time.

## How to Contribute

1. **Open an issue first** — describe the bug or feature
2. **Fork and branch** — create a feature branch from `main`
3. **Follow conventions** — match the existing code style (see below)
4. **Test your changes** — run `pytest` and `python scripts/validate_knowledge.py`
5. **Submit a PR** — reference the issue in your description

## Development Setup

```bash
git clone https://github.com/rezraa/mnemos.git
cd mnemos
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Architecture Rules

These are non-negotiable:

1. **Tools are pure knowledge retrieval.** No regex banks, no fuzzy keyword matching, no language detection. The LLM agent does all reasoning.
2. **Knowledge base is the source of truth.** All algorithm recommendations come from the curated JSON files, not hardcoded logic.
3. **Alternatives must be bidirectional.** If pattern A lists B as an alternative, B must list A.
4. **All knowledge changes must validate.** Run `python scripts/validate_knowledge.py` — 0 errors, 0 warnings.

## Code Style

- Python 3.11+ with type hints
- Tools accept structural descriptions from the agent, not raw code
- No `language` parameter on any tool — the agent understands any language natively
- Keep tools focused: match against JSON knowledge, check memory, return structured results

## License

This project is licensed under [Apache 2.0](LICENSE). The CLA above applies to all contributions.
