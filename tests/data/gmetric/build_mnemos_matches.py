# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Emit the FROZEN S1 recognizer snapshot for mnemos-Gmetric-v1 (story-79321e96).

Provenance record + emitter for the two S1 recognizer artifacts (council REVISE
R1: "a FROZEN mnemos_matches artifact ... recognition frozen INDEPENDENT of gold
vocabulary and hash-pinned"):

  * mnemos_matches_v1.json    -- the frozen recognition: {problem_id -> [signal_id]}
    plus the human-auditable {problem_id -> [signal_text]} so a reviewer can
    confirm each recognised signal describes the problem's shape, from the problem
    alone. Produced by mnemos_engine_bench.build_matches over the frozen
    problems_blind + the live signal index; NEVER reads gmetric_v1.json (the answer
    key), so recognition is provably gold-blind.
  * mnemos_matches_freeze.json -- the S1 trust root: pins mnemos_matches_v1.json
    and the corpus files it derives from. Kept SEPARATE from the S0
    freeze_manifest.json on purpose: grade._verify_substrate enforces an EXACT
    5-pin set (missing/extra fails closed) and build_gmetric_v1.py regenerates that
    manifest with exactly those 5 pins, so adding a 6th pin there would break the
    S0 grader and drift from its builder. A separate S1 manifest meets R1's intent
    (recognition frozen + hash-pinned + tamper-evident) without touching the
    byte-frozen S0 substrate. test_retrieval_bar1 verifies against BOTH.

Determinism: build_matches is a pure function; re-running emits byte-identical
mnemos_matches_v1.json (its own sha256 is stable -- no timestamps in the pinned
body). Run under any PYTHONHASHSEED and the signal ids (content hashes) are
identical.

Firewall: imports only mnemos.* (never coeus.*/othrys.*). No live-DB access.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from mnemos.knowledge.loader import KnowledgeLoader

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import mnemos_engine_bench as eng  # noqa: E402  (path-injected sibling harness)

KDIR = Path(__file__).resolve().parents[3] / "src" / "mnemos" / "knowledge"
PATTERN_FILE, RULES_FILE, COMPLEX_FILE = "structures.json", "decision_rules.json", "complexities.json"

# Corpus-freeze generation (see build_gmetric_v1._VER). recognize() reads the LIVE
# migrated index via the loader, so v2 re-emits the recognizer snapshot the migration
# produced. The problem QUERIES are generation-invariant (problems_blind_v2 == v1 in
# DATA), so eng.build_matches reading the S0 problems is faithful for either generation.
_VER = os.environ.get("MNEMOS_GMETRIC_VERSION", "v1")
_SUF = "" if _VER == "v1" else f"_{_VER}"
MATCHES_OUT = HERE / f"mnemos_matches_{_VER}.json"
FREEZE_OUT = HERE / f"mnemos_matches_freeze{_SUF}.json"
PROBLEMS_IN = HERE / f"problems_blind_{_VER}.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> None:
    loader = KnowledgeLoader(knowledge_dir=KDIR)
    index = loader.get_signal_index()
    id2text = {e["signal_id"]: e["signal_text"] for e in index}

    matches = eng.build_matches(loader)
    # human-auditable companion: the signal TEXT behind each recognised id
    matches_text = {
        pid: [id2text[s] for s in sigs] for pid, sigs in matches.items()
    }

    out = {
        "spec_id": "mnemos-Gmetric-v1-recognizer",
        "story": "story-79321e96",
        "authored_by": "Mnemos",
        "what": (
            "FROZEN gold-blind recognition {problem_id -> matched signal_ids} that "
            "bridges each frozen benchmark query to the Shape-C hydrate path. The "
            "LLM-stand-in for the benchmark (production uses a live LLM). Produced "
            "by mnemos_engine_bench.recognize over problems_blind + the signal "
            "index; independent of gmetric's acceptable_ids (never read here)."
        ),
        "recognition_rule": (
            "signal matched iff (query + authored SHAPE working-memory) overlaps "
            "its text by >= 2 stemmed content tokens, OR query == signal_text "
            "(TK exact leg). SHAPE is a gold-blind restatement of each problem's "
            "shape; the mechanical matcher picks ids, so SHAPE cannot encode a "
            "pattern id. Audit matches_by_signal_text against problems_blind."
        ),
        "corpus_snapshot_sha256": {
            PATTERN_FILE: sha(KDIR / PATTERN_FILE),
            RULES_FILE: sha(KDIR / RULES_FILE),
            COMPLEX_FILE: sha(KDIR / COMPLEX_FILE),
        },
        "n_problems": len(matches),
        "matches": {pid: matches[pid] for pid in sorted(matches)},
        "matches_by_signal_text": {pid: matches_text[pid] for pid in sorted(matches_text)},
    }
    MATCHES_OUT.write_text(canonical_dump(out), encoding="utf-8")

    freeze = {
        "spec_id": "mnemos-Gmetric-v1-recognizer-freeze",
        "story": "story-79321e96",
        "what": (
            "S1 trust root: pins the frozen recognition snapshot + the corpus files "
            "it derives from. Separate from the S0 freeze_manifest.json (which "
            "grade._verify_substrate holds to an exact 5-pin set). Regenerating "
            "this manifest is the only way to move a pin -- a visible, reviewable act."
        ),
        "hash_algo": "sha256",
        "pins": {
            MATCHES_OUT.name: sha(MATCHES_OUT),
            PROBLEMS_IN.name: sha(PROBLEMS_IN),
            PATTERN_FILE: sha(KDIR / PATTERN_FILE),
            RULES_FILE: sha(KDIR / RULES_FILE),
            COMPLEX_FILE: sha(KDIR / COMPLEX_FILE),
        },
    }
    FREEZE_OUT.write_text(canonical_dump(freeze), encoding="utf-8")

    print(f"wrote {MATCHES_OUT.name} sha256={sha(MATCHES_OUT)[:16]}... ({len(matches)} problems)")
    print(f"wrote {FREEZE_OUT.name} pinning {len(freeze['pins'])} files sha256={sha(FREEZE_OUT)[:16]}...")
    total = sum(len(v) for v in matches.values())
    print(f"total recognised signal ids: {total} (mean {total/len(matches):.1f}/problem)")


if __name__ == "__main__":
    main()
