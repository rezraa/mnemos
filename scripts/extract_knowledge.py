#!/usr/bin/env python3
# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""
Extract knowledge from ds-algorithm-primer repository.

Parses HTML topic pages and JS algorithm files to generate
structured knowledge JSON files for the Mnemos knowledge layer.

Usage:
    python scripts/extract_knowledge.py [--primer-path PATH] [--output-dir PATH]
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: BeautifulSoup4 is required. Install with: pip install beautifulsoup4")
    sys.exit(1)


# ── HTML topic pages to parse ──────────────────────────────────────────
TOPIC_PAGES = [
    "arrays.html",
    "strings.html",
    "hashmaps.html",
    "sets.html",
    "linkedlists.html",
    "stacks.html",
    "queues.html",
    "trees.html",
    "graphs.html",
    "dp.html",
    "recursion.html",
    "bigo.html",
]

# ── Mapping from HTML page to structure IDs ────────────────────────────
PAGE_TO_STRUCTURE = {
    "arrays.html": "array",
    "strings.html": "string",
    "hashmaps.html": "hashmap",
    "sets.html": "hashset",
    "linkedlists.html": "linked-list",
    "stacks.html": "stack",
    "queues.html": "queue",
    "trees.html": "tree",
    "graphs.html": "graph",
    "dp.html": "dp",
    "recursion.html": "recursion-backtracking",
    "bigo.html": None,  # Reference page, no direct structure
}


def parse_html_page(html_path: Path) -> dict:
    """Parse a single HTML topic page and extract structured data."""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    result = {
        "file": html_path.name,
        "sections": [],
        "cards": [],
    }

    # Extract section dividers
    for div in soup.select("div.section-divider"):
        label = div.select_one("span.section-label")
        if label:
            result["sections"].append(label.get_text(strip=True))

    # Extract cards with all metadata
    for card in soup.select("div.card"):
        card_data = {}

        # Card title
        title_el = card.select_one("div.card-title")
        if title_el:
            card_data["title"] = title_el.get_text(strip=True)
        else:
            continue  # Skip cards without titles

        # Complexity tags
        time_tags = card.select("span.tag-time")
        space_tags = card.select("span.tag-space")
        if time_tags:
            card_data["time_complexity"] = [t.get_text(strip=True) for t in time_tags]
        if space_tags:
            card_data["space_complexity"] = [t.get_text(strip=True) for t in space_tags]

        # Use-case pills with "Why:" explanations
        use_cases = []
        for uc in card.select("span.use-case"):
            uc_data = {}
            # Get the use-case name (text before the tip span)
            tip = uc.select_one("span.tip")
            if tip:
                # Name is the text content minus the tip
                tip_text = tip.get_text(strip=True)
                full_text = uc.get_text(strip=True)
                uc_data["name"] = full_text.replace(tip_text, "").strip()

                # Extract "Why:" explanation
                why_match = re.search(r"Why:\s*(.+)", tip_text)
                if why_match:
                    uc_data["why"] = why_match.group(1).strip()
                else:
                    uc_data["why"] = tip_text
            else:
                uc_data["name"] = uc.get_text(strip=True)

            use_cases.append(uc_data)

        if use_cases:
            card_data["use_cases"] = use_cases

        # Key points
        key_points_ul = card.select_one("ul.key-points")
        if key_points_ul:
            points = []
            for li in key_points_ul.select("li"):
                points.append(li.get_text(strip=True))
            if points:
                card_data["key_points"] = points

        # Visualizer links
        viz_links = card.select('a[href*="visualizer.html?algo="]')
        if viz_links:
            card_data["visualizer_ids"] = []
            for link in viz_links:
                href = link.get("href", "")
                match = re.search(r"algo=([^&\"]+)", href)
                if match:
                    card_data["visualizer_ids"].append(match.group(1))

        result["cards"].append(card_data)

    return result


def parse_js_algorithm(js_path: Path) -> dict | None:
    """Parse a JS algorithm file and extract metadata using regex."""
    content = js_path.read_text(encoding="utf-8")

    result = {}

    # Extract id
    id_match = re.search(r"id:\s*['\"]([^'\"]+)['\"]", content)
    if id_match:
        result["id"] = id_match.group(1)
    else:
        return None

    # Extract group
    group_match = re.search(r"group:\s*['\"]([^'\"]+)['\"]", content)
    if group_match:
        result["group"] = group_match.group(1)

    # Extract name
    name_match = re.search(r"name:\s*['\"]([^'\"]+)['\"]", content)
    if name_match:
        result["name"] = name_match.group(1)

    # Extract problem names
    problem_names = re.findall(r"name:\s*['\"]([^'\"]+)['\"]", content)
    # First match is the algorithm name, rest are problems
    if len(problem_names) > 1:
        result["problems"] = problem_names[1:]
    else:
        result["problems"] = []

    result["file"] = js_path.name
    return result


def transform_to_structural_signal(use_case_name: str, why: str) -> dict:
    """Transform a problem-specific use case into a structural signal.

    CRITICAL: We convert problem names into structural descriptions.
    E.g., "Two Sum" -> "single-pass complement lookup"
    """
    signal = {
        "original_name": use_case_name,
        "why_explanation": why,
    }

    # Extract structural insight from the "Why:" explanation
    # These are already structural - the "Why:" tells us the pattern
    structural_keywords = []

    why_lower = why.lower() if why else ""

    # Extract key structural concepts from the explanation
    concept_patterns = [
        (r"sorted\s+order", "sorted-input"),
        (r"single\s+pass", "single-pass"),
        (r"complement", "complement-lookup"),
        (r"hash\s*map", "hash-based-lookup"),
        (r"two\s+pointer", "two-pointer"),
        (r"converge?", "convergent"),
        (r"sliding\s+window", "sliding-window"),
        (r"prefix\s+sum", "prefix-sum"),
        (r"frequency\s+map", "frequency-counting"),
        (r"monotonic", "monotonic-invariant"),
        (r"stack", "stack-based"),
        (r"queue", "queue-based"),
        (r"bfs", "breadth-first"),
        (r"dfs", "depth-first"),
        (r"backtrack", "backtracking"),
        (r"recursive", "recursive"),
        (r"greedy", "greedy"),
        (r"binary\s+search", "binary-search"),
        (r"divide\s+and\s+conquer", "divide-and-conquer"),
        (r"dynamic\s+programming|dp", "dynamic-programming"),
        (r"memoiz", "memoization"),
        (r"in[\s-]place", "in-place"),
        (r"o\(1\)\s+space", "constant-space"),
        (r"o\(n\)\s+time", "linear-time"),
    ]

    for pattern, keyword in concept_patterns:
        if re.search(pattern, why_lower):
            structural_keywords.append(keyword)

    signal["structural_keywords"] = structural_keywords
    return signal


def build_structures_json(html_data: list, js_data: list) -> dict:
    """Build the structures.json from extracted HTML and JS data."""
    structures = {}

    for page_data in html_data:
        structure_id = PAGE_TO_STRUCTURE.get(page_data["file"])
        if not structure_id:
            continue

        if structure_id not in structures:
            structures[structure_id] = {
                "id": structure_id,
                "name": structure_id.replace("-", " ").title(),
                "sections": page_data["sections"],
                "patterns_extracted": [],
                "source": "extracted",
            }

        # Extract patterns from cards that have use cases
        for card in page_data["cards"]:
            if "use_cases" not in card:
                continue

            pattern = {
                "card_title": card["title"],
                "time_complexity": card.get("time_complexity", []),
                "space_complexity": card.get("space_complexity", []),
                "visualizer_ids": card.get("visualizer_ids", []),
                "key_points": card.get("key_points", []),
                "structural_signals": [],
            }

            for uc in card["use_cases"]:
                signal = transform_to_structural_signal(
                    uc.get("name", ""), uc.get("why", "")
                )
                pattern["structural_signals"].append(signal)

            structures[structure_id]["patterns_extracted"].append(pattern)

    # Cross-reference with JS algorithm data
    js_by_id = {a["id"]: a for a in js_data if a}
    for struct in structures.values():
        for pattern in struct["patterns_extracted"]:
            for viz_id in pattern.get("visualizer_ids", []):
                if viz_id in js_by_id:
                    js_algo = js_by_id[viz_id]
                    pattern["js_algorithm"] = {
                        "id": js_algo["id"],
                        "group": js_algo.get("group", ""),
                        "name": js_algo.get("name", ""),
                        "problems": js_algo.get("problems", []),
                    }

    return {
        "version": "1.0.0-extracted",
        "source": "ds-algorithm-primer",
        "structures": list(structures.values()),
    }


def build_complexities_json(html_data: list) -> dict:
    """Build complexities.json from extracted HTML data."""
    complexities = {
        "version": "1.0.0-extracted",
        "source": "ds-algorithm-primer",
        "extracted_complexities": [],
    }

    for page_data in html_data:
        for card in page_data["cards"]:
            if card.get("time_complexity") or card.get("space_complexity"):
                complexities["extracted_complexities"].append(
                    {
                        "page": page_data["file"],
                        "card": card["title"],
                        "time": card.get("time_complexity", []),
                        "space": card.get("space_complexity", []),
                    }
                )

    return complexities


def build_decision_rules_json(html_data: list) -> dict:
    """Build decision_rules.json from extracted use-case "Why:" explanations."""
    rules = []

    for page_data in html_data:
        structure_id = PAGE_TO_STRUCTURE.get(page_data["file"])
        if not structure_id:
            continue

        for card in page_data["cards"]:
            if "use_cases" not in card:
                continue

            for uc in card.get("use_cases", []):
                why = uc.get("why", "")
                if not why:
                    continue

                signal = transform_to_structural_signal(
                    uc.get("name", ""), why
                )

                if signal["structural_keywords"]:
                    rule = {
                        "structural_signal": why[:120],
                        "code_indicators": signal["structural_keywords"],
                        "recommended_structure": structure_id,
                        "card_title": card["title"],
                        "source": "extracted",
                    }
                    rules.append(rule)

    return {
        "version": "1.0.0-extracted",
        "source": "ds-algorithm-primer",
        "rules": rules,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract knowledge from ds-algorithm-primer")
    parser.add_argument(
        "--primer-path",
        type=Path,
        default=Path("/Users/rezamalik/Repos/ds-algorithm-primer"),
        help="Path to ds-algorithm-primer repository",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/Users/rezamalik/Repos/mnemos/src/mnemos/knowledge"),
        help="Output directory for JSON files",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge extracted data into existing authored JSON files",
    )
    args = parser.parse_args()

    primer_path = args.primer_path
    output_dir = args.output_dir

    if not primer_path.exists():
        print(f"ERROR: Primer path does not exist: {primer_path}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Parse all HTML topic pages ──────────────────────────────
    print("Parsing HTML topic pages...")
    html_data = []
    for page in TOPIC_PAGES:
        html_path = primer_path / page
        if html_path.exists():
            data = parse_html_page(html_path)
            html_data.append(data)
            print(
                f"  {page}: {len(data['sections'])} sections, "
                f"{len(data['cards'])} cards"
            )
        else:
            print(f"  WARNING: {page} not found")

    # ── Step 2: Parse JS algorithm files ────────────────────────────────
    print("\nParsing JS algorithm files...")
    js_dir = primer_path / "js" / "algorithms"
    js_data = []
    if js_dir.exists():
        for js_file in sorted(js_dir.glob("*.js")):
            if js_file.name == "registry.js":
                continue
            algo = parse_js_algorithm(js_file)
            if algo:
                js_data.append(algo)
        print(f"  Parsed {len(js_data)} algorithm files")
    else:
        print("  WARNING: JS algorithms directory not found")

    # ── Step 3: Generate JSON files ─────────────────────────────────────
    print("\nGenerating knowledge JSON files...")

    # Structures
    structures = build_structures_json(html_data, js_data)
    structures_path = output_dir / "structures.extracted.json"
    with open(structures_path, "w", encoding="utf-8") as f:
        json.dump(structures, f, indent=2, ensure_ascii=False)
    print(f"  {structures_path.name}: {len(structures['structures'])} structures")

    # Complexities
    complexities = build_complexities_json(html_data)
    complexities_path = output_dir / "complexities.extracted.json"
    with open(complexities_path, "w", encoding="utf-8") as f:
        json.dump(complexities, f, indent=2, ensure_ascii=False)
    print(
        f"  {complexities_path.name}: "
        f"{len(complexities['extracted_complexities'])} entries"
    )

    # Decision rules
    rules = build_decision_rules_json(html_data)
    rules_path = output_dir / "decision_rules.extracted.json"
    with open(rules_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)
    print(f"  {rules_path.name}: {len(rules['rules'])} rules")

    # ── Step 4: Summary ─────────────────────────────────────────────────
    total_use_cases = sum(
        len(card.get("use_cases", []))
        for page in html_data
        for card in page["cards"]
    )
    total_key_points = sum(
        len(card.get("key_points", []))
        for page in html_data
        for card in page["cards"]
    )

    print(f"\n{'='*60}")
    print(f"Extraction complete:")
    print(f"  HTML pages parsed:    {len(html_data)}")
    print(f"  JS algorithms parsed: {len(js_data)}")
    print(f"  Total use cases:      {total_use_cases}")
    print(f"  Total key points:     {total_key_points}")
    print(f"  Output directory:     {output_dir}")
    print(f"{'='*60}")

    if not args.merge:
        print(
            "\nNote: Extracted files saved with .extracted.json suffix."
            "\nThe authored structures.json, complexities.json, and"
            "\ndecision_rules.json remain as the primary knowledge files."
            "\nUse --merge to merge extracted data into authored files."
        )


if __name__ == "__main__":
    main()
