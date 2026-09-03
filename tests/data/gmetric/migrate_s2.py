# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""S2 corpus migration: dissolve Mnemos decision_rules into the pattern signal index.

story-3a302579, council f1b39fbd (decisions 2,5) + b781d576 (copy-vs-move).

THE COPY-VS-MOVE CONTRACT (b781d576-decision-2, unanimous tome):
  * structural_signal  -> COPY  the 67 prose sentences VERBATIM onto their
    recommended_pattern's ``structural_signals``. KEPT in decision_rules so
    ``match_structural_signals`` stays byte-callable and the pinned baseline
    (27/77) is preserved. The transitional coexistence (matcher key + index text)
    is the blessed tranche norm, removed with the matcher at S6 -- NOT a DRY
    breach, because the DRY one-source-of-truth is the epic END-state (S6).
  * code_indicators    -> MOVE  onto the pattern as metadata; STRIPPED from
    decision_rules (clean move, no duplication -- the matcher never reads it).
  * recommended_structure -> DROP from every rule. 62/67 equal the pattern's
    parent structure (derivable, fall away); the 5 that differ carry rule-specific
    DS nuance and are RECORDED in migration_proofs (fold rejected -- see below),
    STRIPPED from decision_rules (rank_baseline never reads it).

This RAISES reachability: the 67 problem-language phrasings, absent from the
signal index before (0/67), now route to their pattern (67/67 -> 65 distinct).
It authors NO new pattern and re-points nothing; it relocates existing content.

Idempotent: re-running detects already-migrated prose/metadata and makes no
change (verbatim membership + key presence checks). Firewall: imports only
stdlib; reads/writes only the on-disk mnemos corpus (no othrys.*/coeus.*, no DB).
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

KDIR = Path(__file__).resolve().parents[3] / "src" / "mnemos" / "knowledge"
STRUCTURES = KDIR / "structures.json"
RULES = KDIR / "decision_rules.json"
PROOFS = Path(__file__).resolve().parents[3] / "docs" / "migration_proofs.md"

# The 5 non-derivable recommended_structure diffs (recommended_structure !=
# recommended_pattern's parent structure). DROPPED, not folded: the nuance is
# RULE-specific and CONFLICTS on a shared pattern -- binary-search-on-answer is the
# recommended_pattern of two rules with two different structures (array, derivable;
# graph, this one), so it cannot become a single pattern field without birthing a
# second, self-contradicting source of truth. Each nuance is already implied by the
# migrated code_indicators + the pattern's parent/complexity, so folding adds a
# redundant conflicting field. Provenance is retained here + in migration_proofs.
NON_DERIVABLE_NUANCE = {
    "rule-shortest-path-unweighted": "BFS is realised with a QUEUE (rec_struct=queue); the pattern lives under graph. Nuance carried by code_indicators + the BFS complexity.",
    "rule-dynamic-connectivity": "Union-find is a DISJOINT-SET (rec_struct=disjoint-set); pattern under graph. Nuance carried by code_indicators 'union'/'find'.",
    "rule-min-max-assignment": "binary-search-on-answer applied here uses a bipartite GRAPH feasibility check (rec_struct=graph); the pattern's parent is array, and its OTHER rule (rule-binary-search-on-answer) keeps rec_struct=array -> folding would conflict.",
    "rule-maximize-min-spacing-by-frequency": "task-scheduling's closed form is frequency-driven via a HASHMAP (rec_struct=hashmap); pattern under queue. Nuance carried by code_indicators frequency terms.",
    "rule-persistent-versioned-queries": "A persistent segment tree IS a TREE (rec_struct=tree); the pattern is filed under dp. Nuance carried by the pattern id + code_indicators 'persistent'/'versioned'.",
}


def _read(path: Path) -> tuple[str, bool]:
    """Return (utf-8 text with \\n newlines, had_trailing_newline). Preserves nothing
    about CR: callers re-emit CRLF to match the on-disk corpus style."""
    raw = path.read_bytes().decode("utf-8")
    text = raw.replace("\r\n", "\n")
    return text, text.endswith("\n")


def _dump_structures(obj) -> bytes:
    """Serialise structures.json in its native style: indent=2, ensure_ascii=False,
    CRLF, NO trailing newline (round-trip-proven byte-identical to the source)."""
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    return s.encode("utf-8").replace(b"\n", b"\r\n")


def migrate() -> dict:
    structures = json.loads(STRUCTURES.read_bytes().decode("utf-8"))
    rules = json.loads(RULES.read_bytes().decode("utf-8"))["rules"]

    # pattern_id -> (structure_id, pattern dict reference)
    pat_index: dict[str, tuple[str, dict]] = {}
    for s in structures["structures"]:
        for p in s.get("patterns", []):
            pat_index[p["id"]] = (s["id"], p)

    proofs: list[dict] = []
    code_by_pattern: "OrderedDict[str, list[str]]" = OrderedDict()

    # -- 1. COPY prose onto patterns; accumulate code_indicators per pattern -------
    for rule in rules:
        prose = rule["structural_signal"].strip()
        rp = rule["recommended_pattern"]
        struct_id, pat = pat_index[rp]
        parent = struct_id
        rec_struct = rule.get("recommended_structure")

        sig_list = pat["structural_signals"]
        added = prose not in sig_list
        if added:
            sig_list.append(prose)

        merged = code_by_pattern.setdefault(rp, list(pat.get("code_indicators", [])))
        for ci in rule.get("code_indicators", []):
            if ci not in merged:
                merged.append(ci)

        proofs.append({
            "rule": rule["id"],
            "prose": prose,
            "recommended_pattern": rp,
            "parent_structure": parent,
            "prose_added": added,
            "recommended_structure": rec_struct,
            "structure_derivable": rec_struct == parent,
            "nuance": NON_DERIVABLE_NUANCE.get(rule["id"], ""),
        })

    # -- 2. MOVE code_indicators onto each pattern (inserted after signals) --------
    for rp, merged in code_by_pattern.items():
        _, pat = pat_index[rp]
        if pat.get("code_indicators") == merged:
            continue  # idempotent: already migrated
        rebuilt = OrderedDict()
        for k, v in pat.items():
            if k == "code_indicators":
                continue
            rebuilt[k] = v
            if k == "structural_signals":
                rebuilt["code_indicators"] = merged
        if "code_indicators" not in rebuilt:  # pattern lacked structural_signals key
            rebuilt["code_indicators"] = merged
        pat.clear()
        pat.update(rebuilt)

    STRUCTURES.write_bytes(_dump_structures(structures))

    # -- 3. STRIP code_indicators + recommended_structure from decision_rules ------
    #    Line-level removal preserves the file's hand-authored inline-array style for
    #    every KEPT field (structural_signal/recommended_pattern/alternatives), so the
    #    diff is exactly the removed lines -- no reformat churn.
    text, trailing = _read(RULES)
    kept = [ln for ln in text.split("\n")
            if not ln.lstrip().startswith('"code_indicators"')
            and not ln.lstrip().startswith('"recommended_structure"')]
    out = "\n".join(kept)
    # json.loads validates the surgery produced well-formed JSON before we write it.
    json.loads(out)
    RULES.write_bytes(out.encode("utf-8").replace(b"\n", b"\r\n"))

    return {"proofs": proofs, "code_by_pattern": code_by_pattern,
            "n_rules": len(rules), "n_patterns": len(pat_index)}


if __name__ == "__main__":
    result = migrate()
    added = sum(1 for p in result["proofs"] if p["prose_added"])
    distinct = len({p["recommended_pattern"] for p in result["proofs"]})
    derivable = sum(1 for p in result["proofs"] if p["structure_derivable"])
    print(f"migrated {len(result['proofs'])} rule prose sentences onto {distinct} distinct patterns "
          f"({added} newly added this run)")
    print(f"code_indicators folded onto {len(result['code_by_pattern'])} patterns")
    print(f"recommended_structure: {derivable}/{result['n_rules']} derivable (dropped), "
          f"{result['n_rules']-derivable} non-derivable (dropped + recorded)")
