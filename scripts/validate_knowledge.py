#!/usr/bin/env python3
# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""
Validate the Mnemos knowledge base JSON files.

Checks:
1. Referential integrity (pattern IDs in decision_rules exist in structures)
2. Complexity format (all use Big-O notation)
3. Every structure has at least one pattern
4. Every pattern has structural_signals and applies_when
5. Warns about patterns missing avoid_when or alternatives
6. Cross-checks alternatives point to valid patterns
7. Reports errors and warnings with exit code

Usage:
    python scripts/validate_knowledge.py [--knowledge-dir PATH]

Exit codes:
    0 = all checks pass (warnings may exist)
    1 = errors found
"""

import argparse
import json
import re
import sys
from pathlib import Path


class ValidationReport:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def log(self, msg: str):
        self.info.append(msg)

    def print_report(self):
        if self.info:
            print("\n--- INFO ---")
            for msg in self.info:
                print(f"  [INFO] {msg}")

        if self.warnings:
            print(f"\n--- WARNINGS ({len(self.warnings)}) ---")
            for msg in self.warnings:
                print(f"  [WARN] {msg}")

        if self.errors:
            print(f"\n--- ERRORS ({len(self.errors)}) ---")
            for msg in self.errors:
                print(f"  [ERROR] {msg}")

        print(f"\n{'='*60}")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")
        print(f"  Info:     {len(self.info)}")
        print(f"{'='*60}")

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


def load_json(path: Path) -> dict | None:
    """Load and parse a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}")
        return None


def is_valid_big_o(s: str) -> bool:
    """Check if a string is valid Big-O notation.

    Accepts:
    - Standard: O(1), O(n), O(n log n), O(n^2), O(V+E)
    - Qualified: O(1) average, O(n) worst, O(n) amortized
    - Multi-phase: O(n) build, O(1) query / O(n log n) preprocess, O(log n) per query
    - Ranges: O(1) to O(n)
    - Parametric: O(alpha(n)), O(2^(N/2)), O(m*k), O(d*(n+k))
    - Descriptive: problem-dependent, ~7 bits/element (probabilistic DS)
    """
    if not s:
        return False
    s = s.strip()
    # Accept if it contains at least one O(...) expression
    if re.search(r"O\([^)]+\)", s):
        return True
    # Accept descriptive complexities for generic/probabilistic patterns
    descriptive = [
        "problem-dependent", "exponential", "varies",
        "bits/element", "bits per element",
    ]
    return any(d in s.lower() for d in descriptive)


def validate_structures(data: dict, report: ValidationReport) -> dict[str, set[str]]:
    """Validate structures.json and return mapping of structure -> pattern IDs."""
    if not data:
        report.error("structures.json is missing or empty")
        return {}

    structures = data.get("structures", [])
    if not structures:
        report.error("structures.json has no 'structures' array")
        return {}

    report.log(f"structures.json: {len(structures)} structures found")

    all_pattern_ids: set[str] = set()
    structure_pattern_map: dict[str, set[str]] = {}

    for struct in structures:
        sid = struct.get("id", "<no id>")
        name = struct.get("name", "<no name>")

        # Check required fields
        if not struct.get("id"):
            report.error(f"Structure missing 'id': {struct}")
            continue
        if not struct.get("name"):
            report.error(f"Structure '{sid}' missing 'name'")

        patterns = struct.get("patterns", [])
        structure_pattern_map[sid] = set()

        # Check that structure has at least one pattern
        if not patterns:
            report.warn(f"Structure '{sid}' has no patterns")
            continue

        for pattern in patterns:
            pid = pattern.get("id", "<no id>")

            # Check pattern has ID
            if not pattern.get("id"):
                report.error(f"Pattern in '{sid}' missing 'id'")
                continue

            # Check for duplicate pattern IDs
            if pid in all_pattern_ids:
                report.error(f"Duplicate pattern ID: '{pid}'")
            all_pattern_ids.add(pid)
            structure_pattern_map[sid].add(pid)

            # Check structural_signals
            signals = pattern.get("structural_signals", [])
            if not signals:
                report.error(
                    f"Pattern '{pid}' in '{sid}' missing 'structural_signals'"
                )

            # Check applies_when
            applies = pattern.get("applies_when", [])
            if not applies:
                report.error(
                    f"Pattern '{pid}' in '{sid}' missing 'applies_when'"
                )

            # Warn about missing avoid_when
            if not pattern.get("avoid_when"):
                report.warn(
                    f"Pattern '{pid}' in '{sid}' missing 'avoid_when'"
                )

            # Warn about missing alternatives
            if not pattern.get("alternatives"):
                report.warn(
                    f"Pattern '{pid}' in '{sid}' has no alternatives"
                )

            # Check complexity format
            complexity = pattern.get("complexity", {})
            if complexity:
                time_c = complexity.get("time", "")
                space_c = complexity.get("space", "")
                if time_c and not is_valid_big_o(time_c):
                    report.warn(
                        f"Pattern '{pid}': time complexity '{time_c}' "
                        f"may not be standard Big-O"
                    )
                if space_c and not is_valid_big_o(space_c):
                    report.warn(
                        f"Pattern '{pid}': space complexity '{space_c}' "
                        f"may not be standard Big-O"
                    )

    report.log(f"Total patterns: {len(all_pattern_ids)}")
    return structure_pattern_map


def validate_complexities(data: dict, report: ValidationReport):
    """Validate complexities.json."""
    if not data:
        report.error("complexities.json is missing or empty")
        return

    # Check data structure operations
    ds_ops = data.get("data_structure_operations", {})
    if not ds_ops:
        report.error("complexities.json missing 'data_structure_operations'")
    else:
        report.log(
            f"complexities.json: {len(ds_ops)} data structures with operations"
        )
        for ds_name, ops in ds_ops.items():
            for op_name, complexity_str in ops.items():
                if op_name == "note":
                    continue
                if not is_valid_big_o(complexity_str):
                    report.warn(
                        f"complexities[{ds_name}][{op_name}]: "
                        f"'{complexity_str}' may not be standard Big-O"
                    )

    # Check sorting algorithms
    sorting = data.get("sorting_algorithms", {})
    if not sorting:
        report.error("complexities.json missing 'sorting_algorithms'")
    else:
        report.log(f"complexities.json: {len(sorting)} sorting algorithms")
        for algo_name, algo_data in sorting.items():
            for key in ["time_best", "time_average", "time_worst", "space"]:
                val = algo_data.get(key, "")
                if val and not is_valid_big_o(val):
                    report.warn(
                        f"sorting[{algo_name}][{key}]: "
                        f"'{val}' may not be standard Big-O"
                    )

    # Check input size guidelines
    guidelines = data.get("input_size_guidelines", {})
    if not guidelines:
        report.warn("complexities.json missing 'input_size_guidelines'")
    else:
        report.log(f"complexities.json: {len(guidelines)} input size guidelines")

    # Check constraint-to-complexity guide
    constraints = data.get("constraint_to_complexity_guide", [])
    if not constraints:
        report.warn("complexities.json missing 'constraint_to_complexity_guide'")
    else:
        report.log(
            f"complexities.json: {len(constraints)} constraint-to-complexity rules"
        )


def validate_decision_rules(
    data: dict,
    all_pattern_ids: set[str],
    all_structure_ids: set[str],
    report: ValidationReport,
):
    """Validate decision_rules.json."""
    if not data:
        report.error("decision_rules.json is missing or empty")
        return

    rules = data.get("rules", [])
    if not rules:
        report.error("decision_rules.json has no 'rules' array")
        return

    report.log(f"decision_rules.json: {len(rules)} rules found")

    rule_ids = set()
    for rule in rules:
        rid = rule.get("id", "<no id>")

        # Check required fields
        if not rule.get("id"):
            report.error(f"Rule missing 'id': {rule.get('structural_signal', '')[:50]}")
            continue

        if rid in rule_ids:
            report.error(f"Duplicate rule ID: '{rid}'")
        rule_ids.add(rid)

        if not rule.get("structural_signal"):
            report.error(f"Rule '{rid}' missing 'structural_signal'")

        if not rule.get("code_indicators"):
            report.warn(f"Rule '{rid}' missing 'code_indicators'")

        # Check recommended_pattern exists in structures
        rec_pattern = rule.get("recommended_pattern")
        if rec_pattern and rec_pattern not in all_pattern_ids:
            report.warn(
                f"Rule '{rid}': recommended_pattern '{rec_pattern}' "
                f"not found in structures.json"
            )

        # Check recommended_structure exists
        rec_struct = rule.get("recommended_structure")
        if rec_struct and rec_struct not in all_structure_ids:
            report.warn(
                f"Rule '{rid}': recommended_structure '{rec_struct}' "
                f"not found in structures.json"
            )

        # Check alternatives reference valid patterns
        for alt in rule.get("alternatives", []):
            if alt not in all_pattern_ids:
                report.warn(
                    f"Rule '{rid}': alternative '{alt}' "
                    f"not found in structures.json"
                )


def validate_cross_references(
    structures_data: dict,
    all_pattern_ids: set[str],
    report: ValidationReport,
):
    """Cross-validate alternatives in patterns point to valid pattern IDs."""
    # Also accept top-level structure IDs as valid alternatives
    structure_ids = {s.get("id", "") for s in structures_data.get("structures", [])}
    valid_ids = all_pattern_ids | structure_ids
    for struct in structures_data.get("structures", []):
        for pattern in struct.get("patterns", []):
            pid = pattern.get("id", "")
            for alt in pattern.get("alternatives", []):
                if alt not in valid_ids:
                    report.warn(
                        f"Pattern '{pid}': alternative '{alt}' "
                        f"not found in any structure"
                    )


def main():
    parser = argparse.ArgumentParser(description="Validate Mnemos knowledge base")
    parser.add_argument(
        "--knowledge-dir",
        type=Path,
        default=Path("/Users/rezamalik/Repos/mnemos/src/mnemos/knowledge"),
        help="Path to knowledge directory",
    )
    args = parser.parse_args()

    knowledge_dir = args.knowledge_dir
    report = ValidationReport()

    print(f"Validating knowledge base at: {knowledge_dir}")
    print("=" * 60)

    # Load all JSON files
    structures_data = load_json(knowledge_dir / "structures.json")
    complexities_data = load_json(knowledge_dir / "complexities.json")
    rules_data = load_json(knowledge_dir / "decision_rules.json")

    # Validate structures
    print("\n[1/4] Validating structures.json...")
    structure_pattern_map = validate_structures(structures_data, report)
    all_pattern_ids = set()
    all_structure_ids = set()
    for sid, pids in structure_pattern_map.items():
        all_structure_ids.add(sid)
        all_pattern_ids.update(pids)

    # Validate complexities
    print("[2/4] Validating complexities.json...")
    validate_complexities(complexities_data, report)

    # Validate decision rules
    print("[3/4] Validating decision_rules.json...")
    validate_decision_rules(rules_data, all_pattern_ids, all_structure_ids, report)

    # Cross-validate references
    print("[4/4] Cross-validating references...")
    if structures_data:
        validate_cross_references(structures_data, all_pattern_ids, report)

    # Print report
    report.print_report()

    # Exit code
    if report.has_errors:
        print("\nValidation FAILED with errors.")
        sys.exit(1)
    elif report.warnings:
        print("\nValidation PASSED with warnings.")
        sys.exit(0)
    else:
        print("\nValidation PASSED - all checks clean.")
        sys.exit(0)


if __name__ == "__main__":
    main()
