# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Relationship-manifest MIRROR for the Mnemos repo — stdlib only, no ``othrys``.

Mnemos runs standalone (import firewall). It cannot import the one Othrys-side
reader, so it carries this thin mirror of the manifest SHAPE and a conformance
checker that validates ``knowledge/relationship_manifest.json`` against the Mnemos
corpus without a graph database. The single source of truth for the shape is the
Othrys doc ``RELATIONSHIP_MANIFEST.md``; a drift test on the Othrys side binds
:func:`canonical_shape` here to ``relationship_manifest.canonical_shape()`` there,
and :func:`field_members` to the reader's, so this mirror cannot silently disagree
with the reader on what the contract is. Every Titan carries the same mirror; only
:func:`load_corpus` is Mnemos's own, because Mnemos nests its patterns under
``structures[].patterns``.

Faithful to the reader's fail-closed behaviour, resolved WITHOUT a DB: a target is
resolved against the corpus's own pattern-id set (every locked verb targets a
``patterns`` node); a miss whose ``target_scope`` is not hard-on-miss (``global``
or ``domain_soft``) is carried as a gap; a ``domain``-scope miss raises. It raises
on the same violations as the reader — an unknown verb, a mapped field that
materializes no edge, a dangling explicit-edge source, a malformed / duplicated /
self-referencing field value, an undeclared or ill-typed prop, a prop over its
ceiling, two declarations of one ``(from, to, type)`` with different props, a
non-object node-group entry or an id-less object that declares a reference — and
balances ``declared == materialized + len(gaps)`` on every clean return. The Othrys
reader additionally runs every text prop through its prompt-injection scanner at
seed time; that scanner's pattern list lives in Othrys only (one list, never
copied here).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NamedTuple, Sequence

# ── Mirror of the locked taxonomy (drift-tested against the Othrys reader) ────
TARGET_TABLE = "patterns"
ON_ENUM = ("patterns", "rules")
TARGET_SCOPE_ENUM = ("domain", "domain_soft", "global")
ID_SCOPE_ENUM = ("domain", "global")
RANK_ENUM = ("primary", "alternative")

# A ``target_scope`` decides two orthogonal things — id CONSTRUCTION (prefix vs
# verbatim) and miss DISPOSITION (raise vs spool a gap) — the {prefix|verbatim} x
# {raise|gap} table. These two frozensets are the ONE place each decision lives
# (mirror of the reader), so a scope's cell is chosen by POSITIVE set membership:
#   domain -> (prefix, raise); global -> (verbatim, gap); domain_soft -> (prefix, gap).
# The 4th cell (verbatim + raise) is unused, deliberately omitted (YAGNI).
_VERBATIM_SCOPES = frozenset({"global"})
_HARD_ON_MISS = frozenset({"domain"})

# Mirror of the reader's edge catalog: every edge is one-way, one row per identity.
EDGE_IDENTITY = ("from", "to", "type")
MAX_EDGE_PROPS = 3
MAX_WHEN_PER_EDGE = 8
MAX_WHEN_CHARS = 200
# A ``string`` prop over this refuses (never trims) — a pathological-size backstop
# far above real content, mirrored from the reader.
MAX_TEXT_PROP_CHARS = 4000
PROP_TYPES = ("int", "string", "string_set")


# NamedTuples, not dataclasses: the Othrys drift test execs this file in isolation
# (never registered in ``sys.modules``), where a dataclass cannot resolve its
# annotations.
class PropSpec(NamedTuple):
    """One declared edge prop (mirror). ``derived`` props are never authored."""

    type: str
    required: bool = False
    enum: "tuple[str, ...] | None" = None
    derived: bool = False


class EdgeSpec(NamedTuple):
    """One catalog entry (mirror): from/to node groups and declared props."""

    from_group: str
    to_group: str
    props: Mapping[str, PropSpec] = MappingProxyType({})


_WHEN = PropSpec("string_set")
_ORDINAL = PropSpec("int", derived=True)

_VERB_SPEC: dict[str, EdgeSpec] = {
    "related": EdgeSpec("patterns", TARGET_TABLE, {"ordinal": _ORDINAL}),
    "alternative": EdgeSpec("patterns", TARGET_TABLE,
                            {"reason": PropSpec("string"), "when": _WHEN, "ordinal": _ORDINAL}),
    "uses": EdgeSpec("patterns", TARGET_TABLE),
    "governs": EdgeSpec("patterns", TARGET_TABLE),
    "detects": EdgeSpec("patterns", TARGET_TABLE),
    "realizes": EdgeSpec("patterns", TARGET_TABLE),
    "recommends": EdgeSpec("rules", TARGET_TABLE, {"rank": PropSpec("string", enum=RANK_ENUM)}),
    "triggers": EdgeSpec("rules", TARGET_TABLE),
}
LOCKED_VERBS = tuple(_VERB_SPEC)

# The spool provenance field allowlist — mirrored verbatim from
# othrys._spool.SpoolRecord (kept honest by the Othrys-side drift test).
SPOOL_FIELDS = (
    "domain",
    "signals",
    "query",
    "source_agent",
    "source_tool",
    "origin",
    "project",
    "unmatched",
    "dangling",
)


def canonical_shape() -> dict[str, Any]:
    """The machine-readable SHAPE — must equal the Othrys reader's
    ``canonical_shape()`` (bound by the Othrys-side drift test)."""
    return {
        "verbs": sorted(LOCKED_VERBS),
        "catalog": {
            verb: {
                "from": spec.from_group,
                "to": spec.to_group,
                "props": {
                    name: {
                        "type": p.type,
                        "required": p.required,
                        "enum": sorted(p.enum) if p.enum is not None else None,
                        "derived": p.derived,
                    }
                    for name, p in sorted(spec.props.items())
                },
            }
            for verb, spec in sorted(_VERB_SPEC.items())
        },
        "identity": list(EDGE_IDENTITY),
        "ceilings": {
            "MAX_EDGE_PROPS": MAX_EDGE_PROPS,
            "MAX_TEXT_PROP_CHARS": MAX_TEXT_PROP_CHARS,
            "MAX_WHEN_CHARS": MAX_WHEN_CHARS,
            "MAX_WHEN_PER_EDGE": MAX_WHEN_PER_EDGE,
        },
        "prop_types": sorted(PROP_TYPES),
        "target_table": TARGET_TABLE,
        "on_enum": sorted(ON_ENUM),
        "target_scope_enum": sorted(TARGET_SCOPE_ENUM),
        "id_scope_enum": sorted(ID_SCOPE_ENUM),
        "spool_fields": sorted(SPOOL_FIELDS),
    }


# ── Fail-closed error taxonomy (mirrors the reader) ──────────────────────────
class ManifestError(RuntimeError):
    """Base for every fail-closed manifest refusal."""


class ManifestFormatError(ManifestError):
    """The manifest violates the documented shape."""


class UnknownEdgeType(ManifestFormatError):
    """An edge ``type`` outside the 8 locked verbs."""


class NoOpFieldEdge(ManifestError):
    """A declared ``field_edge`` that materialized zero edges."""


class DanglingTarget(ManifestError):
    """A target whose ``target_scope`` is hard-on-miss (``domain``) resolved to no
    node. (``domain_soft`` shares ``domain``'s prefix but spools a miss as a gap.)"""


class DanglingSource(ManifestError):
    """An explicit edge whose SOURCE resolved to no node. A source is the Titan's
    own within-domain node; a phantom source can never be filled, so it is ALWAYS
    a hard error — never a gap, independent of ``target_scope``."""


class MalformedFieldValue(ManifestFormatError):
    """A PRESENT inline field value that is not a string or a list/tuple of
    strings, or that lists a target twice or (on a ``patterns`` source) its own
    source. Never skipped, coerced or deduplicated. (Absent / ``None`` is not an
    error.)"""


class MalformedCorpus(ManifestError):
    """A non-object node-group entry, or an id-less object that still declares a
    reference for a mapped field (an unfillable within-domain source)."""


class ReferenceConservationError(ManifestError):
    """Totality backstop: ``declared == materialized + len(gaps)`` at return."""


# ── Load ─────────────────────────────────────────────────────────────────────
_KNOWLEDGE_DIR = Path(__file__).resolve().parent
_MANIFEST_PATH = _KNOWLEDGE_DIR / "relationship_manifest.json"
_STRUCTURES_FILE = "structures.json"
_RULES_FILE = "decision_rules.json"
# Mirror the reader's on-disk-input ceilings (CWE-400): a byte cap and a JSON
# depth pre-scan run BEFORE json.loads so a deep body can't RecursionError past
# the taxonomy. Legit manifest depth ~3; 8 gives headroom.
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_MANIFEST_JSON_DEPTH = 8


def _json_depth_ok(text: str, max_depth: int) -> bool:
    """String/escape-aware O(len) JSON depth pre-scan (mirror of the reader's)."""
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{" or ch == "[":
            depth += 1
            if depth > max_depth:
                return False
        elif ch == "}" or ch == "]":
            depth -= 1
    return True


def load_manifest(path: Path | str = _MANIFEST_PATH) -> dict[str, Any]:
    """Parse the manifest JSON, bounded by a byte ceiling and a depth pre-scan.
    Raises :class:`ManifestFormatError` on an over-cap/over-deep/invalid body or a
    non-object top level (a deep-body ``RecursionError`` is caught too)."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise ManifestFormatError(f"cannot stat manifest {p}: {exc}") from exc
    if size > _MAX_MANIFEST_BYTES:
        raise ManifestFormatError(f"manifest {p} is {size} bytes, over the {_MAX_MANIFEST_BYTES}-byte ceiling")
    try:
        raw = p.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:  # ValueError covers invalid-UTF-8 decode
        raise ManifestFormatError(f"cannot read manifest {p}: {exc}") from exc
    if not _json_depth_ok(raw, _MAX_MANIFEST_JSON_DEPTH):
        raise ManifestFormatError(f"manifest {p} JSON nests past the {_MAX_MANIFEST_JSON_DEPTH}-level ceiling")
    try:
        obj = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ManifestFormatError(f"manifest {p} is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ManifestFormatError(f"manifest {p} top level must be an object")
    return obj


def load_corpus(knowledge_dir: Path | str = _KNOWLEDGE_DIR) -> dict[str, Any]:
    """Load the Mnemos corpus into the shape the resolver reads:
    ``{"domain": "mnemos", "patterns": [...], "rules": [...]}``, the patterns
    flattened out of ``structures[].patterns`` in authored order."""
    d = Path(knowledge_dir)
    structures = json.loads((d / _STRUCTURES_FILE).read_text(encoding="utf-8"))["structures"]
    patterns = [p for s in structures for p in s.get("patterns", [])]
    rules = json.loads((d / _RULES_FILE).read_text(encoding="utf-8"))["rules"]
    return {"domain": "mnemos", "patterns": patterns, "rules": rules}


# ── Validate (mirror of the reader's shape checks) ───────────────────────────
_FIELD_EDGE_REQUIRED = frozenset({"field", "type", "on", "target_scope"})
_EXPLICIT_EDGE_REQUIRED = frozenset({"type", "on", "source", "target", "target_scope"})
_PROVENANCE_REQUIRED = {"source_agent", "source_tool", "origin"}


def _prop_value(verb: str, name: str, spec: PropSpec, value: Any, where: str) -> Any:
    """Mirror of the reader: check one authored prop, return its canonical form."""
    label = f"{where}: {verb}.{name}"
    if spec.type == "string_set":
        if not isinstance(value, (list, tuple)):
            raise ManifestFormatError(f"{label} must be a list of strings, got {type(value).__name__}")
        if not value:
            raise ManifestFormatError(f"{label} is empty — omit the key instead")
        if len(value) > MAX_WHEN_PER_EDGE:
            raise ManifestFormatError(f"{label} has {len(value)} entries, over MAX_WHEN_PER_EDGE={MAX_WHEN_PER_EDGE}")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ManifestFormatError(f"{label} entry {item!r} is not a non-empty string")
            if len(item) > MAX_WHEN_CHARS:
                raise ManifestFormatError(f"{label} entry is {len(item)} chars, over MAX_WHEN_CHARS={MAX_WHEN_CHARS}")
        return tuple(sorted(set(value)))
    expected = {"string": str, "int": int}[spec.type]
    if not isinstance(value, expected) or isinstance(value, bool):
        raise ManifestFormatError(f"{label} must be {spec.type}, got {type(value).__name__}")
    if spec.type == "string" and len(value) > MAX_TEXT_PROP_CHARS:
        raise ManifestFormatError(f"{label} is {len(value)} chars, over MAX_TEXT_PROP_CHARS={MAX_TEXT_PROP_CHARS}")
    if spec.enum is not None and value not in spec.enum:
        raise ManifestFormatError(f"{label}={value!r} not in {spec.enum}")
    return value


def _canonical_props(verb: str, props: Mapping[str, Any], where: str) -> dict[str, Any]:
    """Mirror of the reader: count ceiling first, then declared keys, then values."""
    if len(props) > MAX_EDGE_PROPS:
        raise ManifestFormatError(f"{where}: {len(props)} props on one {verb!r} edge, over MAX_EDGE_PROPS={MAX_EDGE_PROPS}")
    declared = {n: p for n, p in _VERB_SPEC[verb].props.items() if not p.derived}
    unknown = set(props) - set(declared)
    if unknown:
        raise ManifestFormatError(f"{where}: unknown keys {sorted(unknown)} — verb {verb!r} declares {sorted(declared)}")
    return {n: _prop_value(verb, n, declared[n], v, where) for n, v in props.items()}


def _authored(edge: Mapping[str, Any], structural: frozenset) -> dict[str, Any]:
    return {k: v for k, v in edge.items() if k not in structural}


def _edge_props(verb: str, edge_props: Mapping[str, Any], member_props: Mapping[str, Any], where: str) -> tuple:
    """Mirror of the reader's per-edge props (without its Othrys-only injection scan)."""
    member = _canonical_props(verb, member_props, where)
    both = set(edge_props) & set(member)
    if both:
        raise ManifestFormatError(f"{where}: {sorted(both)} set on both the edge and its member")
    props = {**edge_props, **member}
    required = {n for n, p in _VERB_SPEC[verb].props.items() if p.required and not p.derived}
    if required - set(props):
        raise ManifestFormatError(f"{where}: {verb!r} edge missing required {sorted(required - set(props))}")
    return tuple(sorted(props.items()))


def _validate_edge_common(edge: Mapping[str, Any], structural: frozenset, where: str) -> None:
    verb = edge.get("type")
    if not isinstance(verb, str) or verb not in _VERB_SPEC:
        raise UnknownEdgeType(
            f"{where}: unknown edge type {verb!r}: only {', '.join(LOCKED_VERBS)}"
        )
    src_table = _VERB_SPEC[verb].from_group
    on = edge.get("on")
    if on not in ON_ENUM:
        raise ManifestFormatError(f"{where}: on={on!r} not in {ON_ENUM}")
    if on != src_table:
        raise ManifestFormatError(
            f"{where}: on={on!r} disagrees with verb {verb!r} (source {src_table!r})"
        )
    if edge.get("target_scope") not in TARGET_SCOPE_ENUM:
        raise ManifestFormatError(f"{where}: bad target_scope {edge.get('target_scope')!r}")
    _canonical_props(verb, _authored(edge, structural), where)


def validate_manifest(m: Mapping[str, Any]) -> None:
    """Fail-closed structural validation, mirroring the reader."""
    if not isinstance(m, Mapping):
        raise ManifestFormatError("manifest must be a mapping")
    if not isinstance(m.get("domain"), str) or not m.get("domain"):
        raise ManifestFormatError("manifest.domain must be a non-empty string")
    ng = m.get("node_groups", {})
    if not isinstance(ng, Mapping):
        raise ManifestFormatError("manifest.node_groups must be an object")
    for group, flags in ng.items():
        if group not in ON_ENUM:
            raise ManifestFormatError(f"node_groups: {group!r} not in {ON_ENUM}")
        if not isinstance(flags, Mapping):
            raise ManifestFormatError(f"node_groups[{group!r}] must be an object")
        if flags.get("id_scope", "domain") not in ID_SCOPE_ENUM:
            raise ManifestFormatError(f"node_groups[{group!r}].id_scope invalid")
        if not isinstance(flags.get("verbatim_id", False), bool):
            raise ManifestFormatError(f"node_groups[{group!r}].verbatim_id must be a bool")
    fe = m.get("field_edges", [])
    if not isinstance(fe, Sequence) or isinstance(fe, (str, bytes)):
        raise ManifestFormatError("manifest.field_edges must be an array")
    for i, e in enumerate(fe):
        where = f"field_edges[{i}]"
        if not isinstance(e, Mapping):
            raise ManifestFormatError(f"{where} must be an object")
        if _FIELD_EDGE_REQUIRED - set(e):
            raise ManifestFormatError(f"{where}: missing {sorted(_FIELD_EDGE_REQUIRED - set(e))}")
        if not isinstance(e["field"], str) or not e["field"]:
            raise ManifestFormatError(f"{where}: field must be a non-empty string")
        _validate_edge_common(e, _FIELD_EDGE_REQUIRED, where)
    ee = m.get("explicit_edges", [])
    if not isinstance(ee, Sequence) or isinstance(ee, (str, bytes)):
        raise ManifestFormatError("manifest.explicit_edges must be an array")
    for i, e in enumerate(ee):
        where = f"explicit_edges[{i}]"
        if not isinstance(e, Mapping):
            raise ManifestFormatError(f"{where} must be an object")
        if _EXPLICIT_EDGE_REQUIRED - set(e):
            raise ManifestFormatError(f"{where}: missing {sorted(_EXPLICIT_EDGE_REQUIRED - set(e))}")
        for k in ("source", "target"):
            if not isinstance(e[k], str) or not e[k]:
                raise ManifestFormatError(f"{where}: {k} must be a non-empty string")
        _validate_edge_common(e, _EXPLICIT_EDGE_REQUIRED, where)
    prov = m.get("provenance", {})
    if not isinstance(prov, Mapping):
        raise ManifestFormatError("manifest.provenance must be an object")
    if _PROVENANCE_REQUIRED - set(prov):
        raise ManifestFormatError(f"provenance missing {sorted(_PROVENANCE_REQUIRED - set(prov))}")
    for k in _PROVENANCE_REQUIRED:
        if not isinstance(prov[k], str) or not prov[k]:
            raise ManifestFormatError(f"provenance.{k} must be a non-empty string")


# ── Resolve (against the corpus id-set — no DB) ──────────────────────────────
def _mk_id(domain: str, raw: str, scope: str, flags: Mapping[str, Any]) -> str:
    # Verbatim iff the scope is in _VERBATIM_SCOPES (``global``); else prefix. So
    # ``domain`` and ``domain_soft`` share the SAME ``<domain>:`` construction.
    if scope in _VERBATIM_SCOPES:
        return raw
    if flags.get("verbatim_id", False):
        return raw
    return f"{domain}:{raw}"


def field_members(obj: Mapping[str, Any], field: str) -> list[tuple[str, dict[str, Any]]]:
    """The ONE member normaliser (verbatim mirror of the reader's): ``field`` as
    ``[(target, props), ...]`` in authored order. A member is a bare string id
    (``props`` is ``{}``) or an object with a non-empty string ``id`` whose other
    keys are its raw props. Absent / ``None`` -> ``[]``; a scalar string is one bare
    member; anything else RAISES :class:`MalformedFieldValue` — never skipped,
    never coerced."""
    val = obj.get(field)
    if val is None:
        return []
    if isinstance(val, str):
        return [(val, {})]
    if not isinstance(val, (list, tuple)):
        raise MalformedFieldValue(
            f"field {field!r} on source {obj.get('id')!r}: value {val!r} is "
            f"{type(val).__name__}, not a string or a list of members"
        )
    members: list[tuple[str, dict[str, Any]]] = []
    for v in val:
        if isinstance(v, str):
            members.append((v, {}))
        elif isinstance(v, Mapping) and isinstance(v.get("id"), str) and v["id"]:
            members.append((v["id"], {k: x for k, x in v.items() if k != "id"}))
        else:
            raise MalformedFieldValue(
                f"field {field!r} on source {obj.get('id')!r}: member {v!r} is "
                f"{type(v).__name__}, not a string id or an object with a non-empty "
                f"string 'id' (references are never coerced)"
            )
    return members


def _distinct_targets(src_id: str, group: str, tgt_ids: Sequence[str], field: str, where: str) -> None:
    """Mirror of the reader: refuse a field value that lists a target twice, or
    whose ``patterns`` source lists itself. List positions ARE the derived
    ``ordinal``, so a duplicate would be silently collapsed; a self-loop is never
    an authored relation. Checked on the constructed ids."""
    if group == TARGET_TABLE and src_id in tgt_ids:
        raise MalformedFieldValue(f"{where}: {field!r} on {src_id!r} lists its own source")
    dupes = sorted(t for t, n in Counter(tgt_ids).items() if n > 1)
    if dupes:
        raise MalformedFieldValue(f"{where}: {field!r} on {src_id!r} lists {dupes} more than once")


_MATERIALIZED = "materialized"
_GAP = "gap"


def resolve(m: Mapping[str, Any], corpus: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a validated manifest against ``corpus``. Returns
    ``{"edges": set[(verb, source, target, props)], "gaps": list[str], "declared":
    int, "materialized": int}``; ``props`` is sorted ``(name, value)`` pairs.

    TOTALITY (mirror of the reader): every directed reference — each inline field
    member and each explicit edge — is routed through the ONE disposition seam,
    which effects exactly one of {materialize, gap, raise}. Edges are one-way and
    keyed by ``(from, to, type)`` (dedup, idempotent). A clean return balances
    ``declared == materialized + len(gaps)``."""
    validate_manifest(m)
    domain = m["domain"]
    if corpus.get("domain") not in (None, domain):
        raise ManifestFormatError(f"corpus domain {corpus.get('domain')!r} != {domain!r}")
    ng = m.get("node_groups", {})
    target_flags = ng.get(TARGET_TABLE, {})
    pattern_ids = {
        _mk_id(domain, p["id"], "domain", ng.get("patterns", {}))
        for p in corpus.get("patterns", [])
        if isinstance(p, Mapping) and "id" in p
    }
    rule_ids = {
        _mk_id(domain, r["id"], "domain", ng.get("rules", {}))
        for r in corpus.get("rules", [])
        if isinstance(r, Mapping) and "id" in r
    }
    node_ids = {"patterns": pattern_ids, "rules": rule_ids}
    edges: dict[tuple[str, str, str], tuple] = {}
    gaps: list[str] = []
    declared = 0
    materialized = 0

    def _dispose(verb, src_id, src_table, tgt_id, tgt_scope, props, where, *, check_source):
        """THE disposition seam — one of {materialize, gap, raise} per reference."""
        nonlocal materialized
        if check_source and src_id not in node_ids[src_table]:
            raise DanglingSource(
                f"{where}: {verb} source {src_id!r} (on {src_table!r}) resolves to no node"
            )
        if tgt_id in pattern_ids:  # every locked verb targets a patterns node
            prior = edges.setdefault((verb, src_id, tgt_id), props)
            if prior != props:
                raise ManifestFormatError(
                    f"{where}: {verb} {src_id!r} -> {tgt_id!r} is declared twice with "
                    f"different props; an edge is one row per (from, to, type)")
            materialized += 1
            return _MATERIALIZED
        if tgt_scope in _HARD_ON_MISS:
            raise DanglingTarget(f"{where}: {tgt_scope}-scope target {tgt_id!r} resolves to no node")
        gaps.append(tgt_id)
        return _GAP

    for i, e in enumerate(m.get("field_edges", [])):
        where = f"field_edges[{i}]"
        group, field, scope, verb = e["on"], e["field"], e["target_scope"], e["type"]
        fe_props = _canonical_props(verb, _authored(e, _FIELD_EDGE_REQUIRED), where)
        src_flags = ng.get(group, {})
        fe_mat = 0
        for obj in corpus.get(group, []):
            if not isinstance(obj, Mapping):
                raise MalformedCorpus(f"{where}: corpus group {group!r} has a non-object entry {obj!r}")
            members = field_members(obj, field)  # probe before skipping (may raise)
            if "id" not in obj:
                if members:
                    raise MalformedCorpus(
                        f"{where}: id-less {group!r} object declares {len(members)} ref(s) in "
                        f"{field!r} but has no id — an unfillable source"
                    )
                continue  # id-less AND no ref -> the ONLY silent skip
            src_id = _mk_id(domain, obj["id"], "domain", src_flags)
            tgt_ids = [_mk_id(domain, raw, scope, target_flags) for raw, _p in members]
            _distinct_targets(src_id, group, tgt_ids, field, where)
            for tgt_id, (_raw, member_props) in zip(tgt_ids, members):
                props = _edge_props(verb, fe_props, member_props, f"{where} {src_id}->{tgt_id}")
                declared += 1
                disp = _dispose(verb, src_id, group, tgt_id, scope, props, where, check_source=False)
                if disp == _MATERIALIZED:
                    fe_mat += 1
        if fe_mat == 0:
            raise NoOpFieldEdge(f"{where}: field {field!r} materialized 0 edges")

    for i, e in enumerate(m.get("explicit_edges", [])):
        where = f"explicit_edges[{i}]"
        group, scope, verb = e["on"], e["target_scope"], e["type"]
        src_id = _mk_id(domain, e["source"], "domain", ng.get(group, {}))
        tgt_id = _mk_id(domain, e["target"], scope, target_flags)
        props = _edge_props(verb, _canonical_props(verb, _authored(e, _EXPLICIT_EDGE_REQUIRED), where), {}, where)
        declared += 1
        _dispose(verb, src_id, _VERB_SPEC[verb].from_group, tgt_id, scope, props, where, check_source=True)

    if declared != materialized + len(gaps):
        raise ReferenceConservationError(
            f"conservation: declared={declared} materialized={materialized} gaps={len(gaps)}"
        )
    edge_set = {(verb, src, tgt, props) for (verb, src, tgt), props in edges.items()}
    return {"edges": edge_set, "gaps": gaps, "declared": declared, "materialized": materialized}


def check(manifest_path: Path | str = _MANIFEST_PATH, knowledge_dir: Path | str = _KNOWLEDGE_DIR) -> dict[str, Any]:
    """Load + validate + resolve the repo's manifest against the repo's corpus.
    Returns the resolution result. Raises fail-closed on any violation — the
    conformance entry point."""
    return resolve(load_manifest(manifest_path), load_corpus(knowledge_dir))
