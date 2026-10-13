# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Facet-catalogue MIRROR for the Mnemos repo — stdlib only, no ``othrys``.

Mnemos runs standalone (import firewall), so it cannot import the Othrys reader
``othrys.facet_catalogue``, which owns the one fleet-wide catalogue SHAPE. This is
a verbatim mirror of that reader's shape and validation; an Othrys-side drift test
binds :func:`canonical_shape` here to the reader's and runs both over the same
fail-closed fixtures, so the two cannot disagree on what a valid catalogue is. The
reader additionally runs every description through Othrys's prompt-injection
scanner at seed time; that pattern list lives in Othrys only (one list, never
copied here).

The VOCABULARY is Mnemos's own: ``facet_catalogue.json`` beside this file declares
the caller-constraint keys ``KnowledgeLoader.filter_by_constraints`` reads. The
tools load it once at import (:mod:`mnemos.tools._shared`), refuse to start on an
invalid catalogue or corpus facet, and report any caller key it does not declare
or value it does not allow (:func:`resolve_constraints`).

See the reader's docstring for the catalogue format and the three kinds.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, NamedTuple

CATALOGUE_NAME = "facet_catalogue.json"
FACET_KINDS = ("complexity_class", "enum", "int_range")
_ENUMERATED_KINDS = ("complexity_class", "enum")
FACET_FIELDS = ("avoid_when", "use_when")
_TOP_FIELDS = ("domain", "facets")
_KEY_FIELDS = ("description", "kind", "synonyms", "values", "wildcard")
_WILDCARD_FIELDS = ("description", "value")

MAX_FACET_KEYS = 32
MAX_VALUES_PER_KEY = 64
MAX_SYNONYMS_PER_KEY = 8
MAX_VALUE_CHARS = 64
MAX_DESCRIPTION_CHARS = 200
# The reader's bounded read (relationship_manifest.load_bounded_json_object) ceilings.
_MAX_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 8

_CATALOGUE_PATH = Path(__file__).resolve().parent / CATALOGUE_NAME


# NamedTuples, not dataclasses: the Othrys drift test execs this file in isolation
# (never registered in ``sys.modules``), where a dataclass cannot resolve its
# annotations.
class FacetSpec(NamedTuple):
    """One declared key (mirror). ``values`` maps each allowed token to its
    description (enumerated kinds only); ``wildcard`` is ``(token, description)``."""

    kind: str
    description: str
    values: "Mapping[str, str] | None" = None
    wildcard: "tuple[str, str] | None" = None
    synonyms: tuple[str, ...] = ()


class FacetCatalogue(NamedTuple):
    """A validated catalogue (mirror): ``specs`` by key, ``names`` mapping every
    declared spelling (key or synonym) to its key."""

    domain: str
    specs: Mapping[str, FacetSpec]
    names: Mapping[str, str]


class FacetCatalogueError(RuntimeError):
    """The catalogue, or a corpus facet, violates the declared shape."""


class UnknownFacetKey(FacetCatalogueError):
    """A corpus facet names an undeclared key (or a caller-only synonym)."""


class DisallowedFacetValue(FacetCatalogueError):
    """A corpus facet value outside its key's kind grammar or declared values."""


def canonical_shape() -> dict[str, Any]:
    """Must equal ``othrys.facet_catalogue.canonical_shape()`` (drift-tested)."""
    return {
        "catalogue_name": CATALOGUE_NAME,
        "top_fields": sorted(_TOP_FIELDS),
        "key_fields": sorted(_KEY_FIELDS),
        "wildcard_fields": sorted(_WILDCARD_FIELDS),
        "kinds": sorted(FACET_KINDS),
        "enumerated_kinds": sorted(_ENUMERATED_KINDS),
        "facet_fields": sorted(FACET_FIELDS),
        "ceilings": {
            "MAX_BYTES": _MAX_BYTES,
            "MAX_JSON_DEPTH": _MAX_JSON_DEPTH,
            "MAX_FACET_KEYS": MAX_FACET_KEYS,
            "MAX_SYNONYMS_PER_KEY": MAX_SYNONYMS_PER_KEY,
            "MAX_VALUES_PER_KEY": MAX_VALUES_PER_KEY,
            "MAX_VALUE_CHARS": MAX_VALUE_CHARS,
            "MAX_DESCRIPTION_CHARS": MAX_DESCRIPTION_CHARS,
        },
    }


# ── Bounded read (mirror of relationship_manifest.load_bounded_json_object) ───
def _json_depth_ok(text: str, max_depth: int) -> bool:
    """String/escape-aware O(len) JSON depth pre-scan, run before ``json.loads`` so
    a deep body is refused rather than driving the parser to ``RecursionError``."""
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


def _load_bounded_json_object(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FacetCatalogueError(f"cannot stat facet catalogue {path}: {exc}") from exc
    if size > _MAX_BYTES:
        raise FacetCatalogueError(f"facet catalogue {path} is {size} bytes, over the {_MAX_BYTES}-byte ceiling")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:  # ValueError covers invalid-UTF-8 decode
        raise FacetCatalogueError(f"cannot read facet catalogue {path}: {exc}") from exc
    if not _json_depth_ok(raw, _MAX_JSON_DEPTH):
        raise FacetCatalogueError(f"facet catalogue {path} JSON nests past the {_MAX_JSON_DEPTH}-level ceiling")
    try:
        obj = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise FacetCatalogueError(f"facet catalogue {path} is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise FacetCatalogueError(f"facet catalogue {path} top level must be an object")
    return obj


# ── Catalogue validation (mirror of the reader) ──────────────────────────────
def _text(value: Any, ceiling: int, ceiling_name: str, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise FacetCatalogueError(f"{where}: {value!r} is not a non-empty string")
    if len(value) > ceiling:
        raise FacetCatalogueError(f"{where}: {len(value)} chars, over {ceiling_name}={ceiling}")
    if value != value.strip():
        raise FacetCatalogueError(f"{where}: {value!r} has surrounding whitespace")
    return value


def _token(value: Any, where: str) -> str:
    return _text(value, MAX_VALUE_CHARS, "MAX_VALUE_CHARS", where)


def _description(value: Any, where: str) -> str:
    return _text(value, MAX_DESCRIPTION_CHARS, "MAX_DESCRIPTION_CHARS", f"{where}.description")


def _distinct(tokens: Iterable[str], where: str) -> None:
    seen: dict[str, str] = {}
    for tok in tokens:
        folded = tok.casefold()
        if folded in seen:
            raise FacetCatalogueError(f"{where}: {tok!r} and {seen[folded]!r} collide ignoring case")
        seen[folded] = tok


def _values(raw: Any, kind: str, where: str) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise FacetCatalogueError(f"{where} must be an object of value -> description")
    if len(raw) > MAX_VALUES_PER_KEY:
        raise FacetCatalogueError(f"{where}: {len(raw)} values, over MAX_VALUES_PER_KEY={MAX_VALUES_PER_KEY}")
    if not raw:
        raise FacetCatalogueError(f"{where} is empty — a value set over nothing never matches")
    values = {_token(tok, f"{where} key {tok!r}"): _description(desc, f"{where}.{tok}")
              for tok, desc in raw.items()}
    if kind == "complexity_class":
        bad = [tok for tok in values if not _is_complexity_class(tok)]
        if bad:
            raise FacetCatalogueError(f"{where}: {bad} not of the form 'O(...)'")
    _distinct(values, where)
    return values


def _wildcard(raw: Any, where: str) -> tuple[str, str]:
    if not isinstance(raw, Mapping) or set(raw) != set(_WILDCARD_FIELDS):
        raise FacetCatalogueError(f"{where} must be an object with exactly {list(_WILDCARD_FIELDS)}")
    return _token(raw["value"], f"{where}.value"), _description(raw["description"], where)


def _key_spec(key: str, raw: Any) -> FacetSpec:
    where = f"facets.{key}"
    if not isinstance(raw, Mapping):
        raise FacetCatalogueError(f"{where} must be an object")
    unknown = set(raw) - set(_KEY_FIELDS)
    if unknown:
        raise FacetCatalogueError(f"{where}: unknown fields {sorted(unknown)}; allowed {list(_KEY_FIELDS)}")
    kind = raw.get("kind")
    if kind not in FACET_KINDS:
        raise FacetCatalogueError(f"{where}.kind={kind!r} not in {FACET_KINDS}")
    description = _description(raw.get("description"), where)
    values = None
    if kind in _ENUMERATED_KINDS:
        if "values" not in raw:
            raise FacetCatalogueError(f"{where}: a {kind} key must declare its values")
        values = _values(raw["values"], kind, f"{where}.values")
    elif "values" in raw:
        raise FacetCatalogueError(f"{where}: values are declared only for {_ENUMERATED_KINDS}, not {kind!r}")
    wildcard = _wildcard(raw["wildcard"], f"{where}.wildcard") if "wildcard" in raw else None
    if wildcard is not None and values is not None:
        _distinct([*values, wildcard[0]], f"{where}.wildcard")
    synonyms_raw = raw.get("synonyms", [])
    if not isinstance(synonyms_raw, list):
        raise FacetCatalogueError(f"{where}.synonyms must be a list")
    if len(synonyms_raw) > MAX_SYNONYMS_PER_KEY:
        raise FacetCatalogueError(
            f"{where}.synonyms: {len(synonyms_raw)} entries, over MAX_SYNONYMS_PER_KEY={MAX_SYNONYMS_PER_KEY}")
    synonyms = tuple(_token(s, f"{where}.synonyms[{i}]") for i, s in enumerate(synonyms_raw))
    return FacetSpec(kind, description, MappingProxyType(values) if values is not None else None,
                     wildcard, synonyms)


def validate_catalogue(raw: Any) -> FacetCatalogue:
    """Validate a parsed catalogue and return it resolved (mirror)."""
    if not isinstance(raw, Mapping):
        raise FacetCatalogueError(f"catalogue must be an object, got {type(raw).__name__}")
    unknown = set(raw) - set(_TOP_FIELDS)
    if unknown:
        raise FacetCatalogueError(f"catalogue: unknown fields {sorted(unknown)}; allowed {list(_TOP_FIELDS)}")
    domain = raw.get("domain")
    if not isinstance(domain, str) or not domain:
        raise FacetCatalogueError("catalogue.domain must be a non-empty string")
    facets = raw.get("facets")
    if not isinstance(facets, Mapping):
        raise FacetCatalogueError("catalogue.facets must be an object")
    if len(facets) > MAX_FACET_KEYS:
        raise FacetCatalogueError(f"catalogue declares {len(facets)} keys, over MAX_FACET_KEYS={MAX_FACET_KEYS}")
    specs: dict[str, FacetSpec] = {}
    names: dict[str, str] = {}
    for key, raw_spec in facets.items():
        _token(key, f"facets key {key!r}")
        spec = specs[key] = _key_spec(key, raw_spec)
        for name in (key, *spec.synonyms):
            if name in names:
                raise FacetCatalogueError(
                    f"facets.{key}: {name!r} is already declared by {names[name]!r} — "
                    f"one spelling must resolve to one key")
            names[name] = key
    _distinct(names, "catalogue names")
    return FacetCatalogue(domain, MappingProxyType(specs), MappingProxyType(names))


def load_catalogue(path: Path | str = _CATALOGUE_PATH) -> FacetCatalogue:
    """Read (bounded) and validate a catalogue file; Mnemos's own by default."""
    return validate_catalogue(_load_bounded_json_object(Path(path)))


# ── Facet values (mirror of the reader) ──────────────────────────────────────
def _digits(text: str) -> bool:
    return text.isascii() and text.isdigit()


def _is_int_range(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if not isinstance(value, str):
        return False
    if value.endswith("+"):
        return _digits(value[:-1])
    lo, sep, hi = value.partition("-")
    if not sep:
        return _digits(value)
    return _digits(lo) and _digits(hi) and int(lo) <= int(hi)


def _is_complexity_class(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("O(") and value.endswith(")") and len(value) > 3


def _value_ok(spec: FacetSpec, value: Any) -> bool:
    if spec.wildcard is not None and value == spec.wildcard[0]:
        return True
    if spec.values is not None:
        return isinstance(value, str) and value in spec.values
    return _is_int_range(value)


def validate_facets(catalogue: FacetCatalogue, patterns: Iterable[Mapping[str, Any]]) -> int:
    """Check every facet on ``patterns`` against ``catalogue``; return how many
    were checked (mirror)."""
    checked = 0
    for pattern in patterns:
        pid = pattern.get("id") if isinstance(pattern, Mapping) else None
        for field in FACET_FIELDS:
            items = pattern.get(field) if isinstance(pattern, Mapping) else None
            for i, facet in enumerate(items if isinstance(items, list) else ()):
                if not isinstance(facet, Mapping):
                    continue
                where = f"{pid}.{field}[{i}]"
                if not facet:
                    raise FacetCatalogueError(f"{where}: an empty facet never matches")
                for key, value in facet.items():
                    spec = catalogue.specs.get(key)
                    if spec is None:
                        hint = (f" (a synonym of {catalogue.names[key]!r}; the corpus uses the key)"
                                if key in catalogue.names else "")
                        raise UnknownFacetKey(
                            f"{where}: key {key!r} is not declared in the {catalogue.domain} "
                            f"facet catalogue{hint}")
                    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
                        raise DisallowedFacetValue(
                            f"{where}: {key} value is {len(value)} chars, over MAX_VALUE_CHARS={MAX_VALUE_CHARS}")
                    if not _value_ok(spec, value):
                        raise DisallowedFacetValue(
                            f"{where}: {key}={value!r} is not a valid {spec.kind} value"
                            + (f" (declared: {sorted(spec.values)})" if spec.values else ""))
                checked += 1
    return checked


# ── Caller side (Mnemos only: the reader has no caller) ──────────────────────
_CALLER_INT_EXAMPLE = 1000000


class ResolvedConstraints(NamedTuple):
    """Caller constraints resolved against a catalogue. ``values`` maps each declared
    key to its canonical value and is the only thing a filter may read; ``invalid``
    maps each caller spelling whose value the catalogue does not allow to a JSON-safe
    report. An invalid value is never applied (fail open, never a wrong filter)."""

    values: Mapping[str, Any]
    invalid: Mapping[str, dict]


def undeclared(catalogue: FacetCatalogue, keys: Iterable[Any]) -> list[Any]:
    """The caller keys that are neither a declared key nor a synonym, in order."""
    return [k for k in keys if k not in catalogue.names]


def _caller_int(value: Any) -> int | None:
    """A caller ``int_range`` value is ONE non-negative whole number: the bound the
    filter compares against. Any exact spelling of one (an int, a whole float, an
    ASCII-digit string, as JSON transports often stringify numbers) normalises to
    that int. A range such as ``'1-5'`` or ``'10+'`` is the CORPUS facet grammar and
    names no single bound, so it is refused rather than guessed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str) and len(value) <= MAX_VALUE_CHARS and _digits(value.strip()):
        return int(value.strip())
    return None


def _caller_token(spec: FacetSpec, value: Any) -> str | None:
    """The declared token (or wildcard) *value* names, ignoring case and surrounding
    space. Unambiguous because a catalogue's tokens are distinct ignoring case."""
    if not isinstance(value, str) or len(value) > MAX_VALUE_CHARS:
        return None
    folded = value.strip().casefold()
    return next((tok for tok in _allowed(spec) if tok.casefold() == folded), None)


def _allowed(spec: FacetSpec) -> list[str]:
    return [*(spec.values or ()), *([spec.wildcard[0]] if spec.wildcard else [])]


def _echo(value: Any) -> Any:
    """A caller value, bounded and JSON-safe, for the invalid-value report."""
    if isinstance(value, str):
        return value[:MAX_VALUE_CHARS]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return f"<{type(value).__name__}>"


def _invalid_report(spec: FacetSpec, value: Any) -> dict:
    if spec.kind == "int_range":
        return {"value": _echo(value), "example": _CALLER_INT_EXAMPLE,
                "reason": "not one non-negative whole number (a range such as '1-5' or "
                          "'10+' names no single bound)"}
    return {"value": _echo(value), "allowed": _allowed(spec),
            "reason": f"not a declared {spec.kind} value (matched ignoring case)"}


def resolve_constraints(catalogue: FacetCatalogue, constraints: Mapping[Any, Any]) -> ResolvedConstraints:
    """Resolve caller *constraints* against *catalogue*, by kind.

    Each declared spelling present with a non-``None`` value is resolved: an
    enumerated kind to its canonical declared token (case-insensitive), an
    ``int_range`` to one whole number. A key's own spelling takes precedence over its
    synonyms (in declared order), whatever the caller's order. Undeclared keys are
    :func:`undeclared`'s concern and are skipped here. Idempotent on its own output."""
    values: dict[str, Any] = {}
    invalid: dict[str, dict] = {}
    for key, spec in catalogue.specs.items():
        for name in (key, *spec.synonyms):
            value = constraints.get(name)
            if value is None:
                continue
            canonical = _caller_int(value) if spec.kind == "int_range" else _caller_token(spec, value)
            if canonical is None:
                invalid[name] = _invalid_report(spec, value)
            else:
                values.setdefault(key, canonical)
    return ResolvedConstraints(MappingProxyType(values), MappingProxyType(invalid))
