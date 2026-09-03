# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Freeze the THREE locked legs of mnemos-Gmetric-v1 AFTER the baseline is read.

council f1b39fbd-decision-4: "THREE LOCKED legs set AFTER the baseline is read
(delta>=X, recall@10>=Y, wins>=Z)". bb55bb05-decision-2: mirror coeus's
primary-delta + design-works-floor + distribution-robustness.

These are S1's BAR. S0 SETS them; it does not run the engine. Calibrated from the
measured baseline and the two ceilings, so a real Shape-C win clears them and a
marginal/noise result fails. Once frozen here, the bar is locked.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Corpus-freeze generation (see build_gmetric_v1._VER). The legs are calibrated
# from the baseline, which is generation-invariant (the matcher keeps its
# structural_signal after the S2 migration), so v2 legs equal v1 legs by value;
# the re-freeze re-emits them against the v2 substrate for a self-consistent pin set.
_VER = os.environ.get("MNEMOS_GMETRIC_VERSION", "v1")
_SUF = "" if _VER == "v1" else f"_{_VER}"
BASELINE_IN = HERE / f"baseline_matcher_pinned{_SUF}.json"
GMETRIC_IN = HERE / f"gmetric_{_VER}.json"
OUT = HERE / f"locked_legs_{_VER}.json"


def canonical_dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> None:
    base = json.loads(BASELINE_IN.read_text(encoding="utf-8"))
    gm = json.loads(GMETRIC_IN.read_text(encoding="utf-8"))

    core = base["RESULT_baseline"]
    denom = core["denominator_E_golds"]                 # 77 E-golds
    b_recall10 = core["recall"]["10"]                   # 0.3506
    b_covered10 = core["covered"]["10"]                 # 27
    n_problems = gm["5_reproducibility"]["n_problems"]  # 40
    content = gm["2_denominators"]["content_method_independent"]
    ceiling = gm["2_denominators"]["matcher_reachable_ceiling_method_dependent"]

    # ---- leg calibration ----
    DELTA_BAR = 0.25          # clearly beyond noise; baseline PB+TK gap alone is 0.61 of the set
    FLOOR = 0.60              # "the new path surfaces a majority of what is reachable" (coeus used 0.50;
                             #  raised: the engine matches pattern signals directly -> full-canon headroom,
                             #  not the 107/179 rule-wired ceiling the baseline is bounded by)
    DIST_MIN = 35            # of 40 problems (coeus: >=22/25 = 0.88; 35/40 = 0.875)

    delta_min_covered = b_covered10 + math.ceil(DELTA_BAR * denom)
    floor_min_covered = math.ceil(FLOOR * denom)

    legs = {
        "spec_id": "mnemos-Gmetric-v1-locked-legs",
        "story": "story-63e99042",
        "status": "LOCKED",
        "set_after": "baseline_matcher_pinned.json (legs calibrated from the measured baseline, never before)",
        "is_the_bar_for": "S1 engine (Shape-C signal-index port). S0 sets this bar; it does not run the engine.",
        "baseline_snapshot": {
            "recall_at_10": b_recall10, "covered_at_10": b_covered10, "denominator_E_golds": denom,
            "by_qclass_at_10": {qc: v["10"] for qc, v in core["by_qclass"].items()},
            "not_a_strawman": "PA (rule-prose) baseline = 27/27 = 1.0; the matcher answers its own idiom perfectly.",
        },
        "ceilings_for_interpretation": {
            "content_coverage_E_over_total": content["content_coverage_E_over_total"],
            "matcher_reachable_ceiling_recall": ceiling["baseline_recall_ceiling"],
            "engine_content_ceiling": ("~1.0 of the 77 E-golds: every E-gold's acceptable_ids are real "
                                       "patterns reachable by a full-canon signal index (not bounded by the "
                                       "107/179 rule wiring)."),
        },
        "LEG_1_primary_delta": {
            "rule": f"recall@10(engine) - recall@10(baseline={b_recall10}) >= {DELTA_BAR}",
            "equivalently": f"engine covers >= {delta_min_covered} of {denom} E-golds (baseline {b_covered10} + "
                            f"{math.ceil(DELTA_BAR*denom)})",
            "delta_bar": DELTA_BAR,
            "engine_min_recall_at_10": round(b_recall10 + DELTA_BAR, 4),
            "engine_min_covered_at_10": delta_min_covered,
            "why": "The PB+TK problem-language/token gap the baseline scores 0 on is 47/77 of the set; "
                   "recovering ~40% of the headroom is a clearly-not-noise win.",
        },
        "LEG_2_design_works_floor": {
            "rule": f"recall@10(engine) >= {FLOOR}",
            "equivalently": f"engine covers >= {floor_min_covered} of {denom} E-golds",
            "floor": FLOOR,
            "engine_min_covered_at_10": floor_min_covered,
            "why": "Establishes the new path surfaces a majority of what is reachable, not merely that it "
                   "beats a matcher that is near-zero off its own idiom.",
        },
        "LEG_3_distribution_wins": {
            "rule": f"engine covered@10 >= baseline covered@10 on >= {DIST_MIN} of {n_problems} problems",
            "min_problems_ge_baseline": DIST_MIN,
            "n_problems": n_problems,
            "why": "Guards against a win concentrated in a few problems AND against regressing the 12 PA "
                   "problems the matcher already covers. Because PA is already maxed, the LEG_1 delta can "
                   "only be earned in PB/TK/CE -- the win is forced to land in the target classes.",
        },
        "verdict_rule": "PASS = LEG_1 AND LEG_2 AND LEG_3. Any one failing = NOT a pass; return to council.",
        "re_freeze": "On corpus/benchmark drift (any pinned hash changes) re-freeze v1->v2; the v1 E-set "
                     "must stay covered@10 by the engine (eviction FAILS).",
    }
    OUT.write_text(canonical_dump(legs), encoding="utf-8")
    print("=== LOCKED LEGS (set after baseline) ===")
    print(f"LEG_1 primary delta : engine recall@10 >= {round(b_recall10+DELTA_BAR,4)} "
          f"(>= {delta_min_covered}/{denom}); delta >= {DELTA_BAR}")
    print(f"LEG_2 design floor  : engine recall@10 >= {FLOOR} (>= {floor_min_covered}/{denom})")
    print(f"LEG_3 distribution  : engine covered@10 >= baseline on >= {DIST_MIN}/{n_problems} problems")
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
