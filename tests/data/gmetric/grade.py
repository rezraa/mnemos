# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Deterministic grader for mnemos-Gmetric-v1 (story-63e99042).

ONE grader (DRY). It grades ANY method that maps a frozen query to a rank-ordered
list of corpus pattern ids, against the frozen concept map in gmetric_v1.json:

    A gold is COVERED@k iff its acceptable_ids intersect the method's top-k.
    recall@k = (# E-golds covered) / (# E-golds).  Only E golds are scored.

The Shape-C hydrate engine reuses grade(method_fn, ...) verbatim over the frozen
queries + corpus. The legacy match_structural_signals matcher that once produced
the baseline was deleted at S6 (story-24ba71ef); its baseline result core is now
permanently frozen in baseline_matcher_pinned_v2.json and read via
load_pinned_baseline() -- never recomputed, because no matcher remains to run.

Every number is stratified by qclass, register, and structure -- never a single
pooled mean (m-e8ccb163). Determinism: grade runs with a FRESH KnowledgeLoader and
is byte-identical across fresh loaders; run under any PYTHONHASHSEED and the
result core is stable (the invariant is the result core, not any file's sha256).

Tamper-evidence: _verify_substrate reads its pins from the EXTERNAL
freeze_manifest.json (the trust root), never from gmetric_v1.json (which it grades
against), and fails closed on ANY drift -- gmetric included (CWE-345).

Firewall: imports only mnemos.*, never othrys.*/coeus.*. No live-DB access.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

from mnemos.knowledge.loader import KnowledgeLoader

HERE = Path(__file__).resolve().parent
KDIR = Path(__file__).resolve().parents[3] / "src" / "mnemos" / "knowledge"
PATTERN_FILE, RULES_FILE, COMPLEX_FILE = "structures.json", "decision_rules.json", "complexities.json"

# Corpus-freeze generation (see build_gmetric_v1._VER). Default v1 = S0 provenance;
# MNEMOS_GMETRIC_VERSION=v2 grades against the post-migration re-freeze.
_VER = os.environ.get("MNEMOS_GMETRIC_VERSION", "v1")
_SUF = "" if _VER == "v1" else f"_{_VER}"

PROBLEMS_IN = HERE / f"problems_blind_{_VER}.json"
GMETRIC_IN = HERE / f"gmetric_{_VER}.json"
FREEZE_MANIFEST = HERE / f"freeze_manifest{_SUF}.json"
BASELINE_OUT = HERE / f"baseline_matcher_pinned{_SUF}.json"

KS = (10, 5)  # primary, secondary


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_path(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def canonical_dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


# --------------------------------------------------------------------------- #
# FROZEN BASELINE: the legacy matcher's result core, read from the pin.
# --------------------------------------------------------------------------- #

def load_pinned_baseline() -> dict:
    """The FROZEN matcher baseline result core (``RESULT_baseline``), read from
    the pinned artifact.

    The legacy exact-substring matcher (``match_structural_signals``) that
    produced this baseline was deleted at S6 (story-24ba71ef); the baseline is
    permanently frozen at 27/77, so its per-problem and stratified grades are
    read from the pin -- never recomputed, because no matcher remains to run.
    Consumers that once graded ``rank_baseline`` live now read this instead
    (parallel to the locked legs' ``baseline_snapshot``)."""
    return json.loads(BASELINE_OUT.read_text(encoding="utf-8"))["RESULT_baseline"]


# --------------------------------------------------------------------------- #
# GRADER
# --------------------------------------------------------------------------- #

def _verify_substrate() -> dict:
    """Prove the on-disk substrate == the frozen pins in the EXTERNAL manifest.

    Pins are read from freeze_manifest.json -- NEVER from gmetric_v1.json. gmetric
    holds the scored answer key (acceptable_ids) and the recall denominator, so it
    is a certified artifact, not the certifier: reading its own pin from it would be
    circular trust (CWE-345) and a same-Titan later story could widen a gold or flip
    an E->B in gmetric and still pass. Here EVERY pinned file is hashed against the
    external manifest -- gmetric INCLUDED -- and ANY drift, a missing pin, or an
    unverified extra pin fails closed and INVALIDATES the metric."""
    if not FREEZE_MANIFEST.exists():
        raise SystemExit(f"MISSING FREEZE MANIFEST ({FREEZE_MANIFEST.name}); metric cannot be "
                         "verified. Run build_gmetric_v1.py to emit it.")
    pins = json.loads(FREEZE_MANIFEST.read_text(encoding="utf-8"))["pins"]
    paths = {
        PROBLEMS_IN.name: PROBLEMS_IN,
        GMETRIC_IN.name: GMETRIC_IN,
        PATTERN_FILE: KDIR / PATTERN_FILE,
        RULES_FILE: KDIR / RULES_FILE,
        COMPLEX_FILE: KDIR / COMPLEX_FILE,
    }
    missing = sorted(set(paths) - set(pins))
    extra = sorted(set(pins) - set(paths))
    if missing or extra:
        raise SystemExit(f"FREEZE MANIFEST pin set mismatch -- missing {missing}, unverified extra "
                         f"{extra}; metric INVALID.")
    checks = {name: {"cur": sha_path(p), "pin": pins[name]} for name, p in paths.items()}
    for c in checks.values():
        c["match"] = c["cur"] == c["pin"]
    if not all(c["match"] for c in checks.values()):
        raise SystemExit("SUBSTRATE DRIFT -- on-disk hashes != frozen manifest pins; metric "
                         "INVALID.\n" + json.dumps(checks, indent=2))
    return checks


def grade(method_fn, method_name: str) -> dict:
    """Grade one method over the frozen benchmark. Fresh loader each call.
    Returns a deterministic result CORE (no timestamps) suitable for hashing."""
    problems = json.loads(PROBLEMS_IN.read_text(encoding="utf-8"))["problems"]
    gmetric = json.loads(GMETRIC_IN.read_text(encoding="utf-8"))
    reach_map = gmetric["reachable_set_map"]

    # E-golds grouped by problem (only E golds are scored)
    e_by_problem: dict[str, list[dict]] = defaultdict(list)
    for row in reach_map:
        if row["verdict"] == "E":
            e_by_problem[row["problem"]].append(row)

    loader = KnowledgeLoader(knowledge_dir=KDIR)

    per_problem: dict[str, dict] = {}
    # aggregate counters per k
    agg = {k: 0 for k in KS}
    denom = 0
    # strata: qclass / register / structure -> per k {covered, of}
    strat = {dim: defaultdict(lambda: {k: {"covered": 0, "of": 0} for k in KS})
             for dim in ("qclass", "register", "structure")}

    for prob in problems:
        pid = prob["id"]
        ranked = method_fn(loader, prob["query"])
        topk = {k: ranked[:k] for k in KS}
        egolds = e_by_problem.get(pid, [])
        prow = {"qclass": prob["qclass"], "register": prob["register"],
                "n_gold_E": len(egolds), "ranked_top10": ranked[:10], "grades": {}}
        for k in KS:
            tk = set(topk[k])
            covered_here = []
            for g in egolds:
                hit = bool(set(g["acceptable_ids"]) & tk)
                if hit:
                    covered_here.append(g["canonical"])
                strat["qclass"][prob["qclass"]][k]["of"] += 1
                strat["register"][prob["register"]][k]["of"] += 1
                strat["structure"][g["structure"]][k]["of"] += 1
                if hit:
                    strat["qclass"][prob["qclass"]][k]["covered"] += 1
                    strat["register"][prob["register"]][k]["covered"] += 1
                    strat["structure"][g["structure"]][k]["covered"] += 1
            prow["grades"][str(k)] = {"covered": len(covered_here), "of": len(egolds),
                                      "covered_golds": sorted(covered_here)}
            agg[k] += len(covered_here)
        per_problem[pid] = prow
        denom += len(egolds)

    recall = {k: round(agg[k] / denom, 4) if denom else 0.0 for k in KS}

    def _finalize(d):
        return {key: {str(k): {"covered": v[k]["covered"], "of": v[k]["of"],
                               "recall": round(v[k]["covered"] / v[k]["of"], 4) if v[k]["of"] else 0.0}
                      for k in KS}
                for key, v in sorted(d.items())}

    core = {
        "method": method_name,
        "denominator_E_golds": denom,
        "recall": {str(k): recall[k] for k in KS},
        "covered": {str(k): agg[k] for k in KS},
        "by_qclass": _finalize(strat["qclass"]),
        "by_register": _finalize(strat["register"]),
        "by_structure": _finalize(strat["structure"]),
        "per_problem": {pid: per_problem[pid] for pid in sorted(per_problem)},
    }
    return core
