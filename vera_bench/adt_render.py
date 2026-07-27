"""Render a test-case ADT value into each comparison language's own idiom.

The twelve ADT problems ask the *model* to define the data type, and every
language's idiom for that is different. The canonical solutions prove it:
Vera declares `data List { Nil, Cons(Int, List) }`, AILANG writes
`type MyList = MyNil | MyCons(int, MyList)`, TypeScript uses a tagged
union with named fields, Python uses classes, and Aver frequently reaches
for its built-in `List<Int>` and `Option<Int>` instead of declaring
anything at all.

So a single test-case value — written once, against the canonical
constructor names in the problem's `adt` block — has to be rendered five
different ways. This module owns that translation. The Vera side lives in
`vera_wrapper.py`, because it additionally has to match against the
model's own declaration to build the literal.

Names are matched case-insensitively and, failing that, by a near-name
heuristic — a unique declared name that extends the canonical one, which
is how AILANG's `MyNil` and Python's `NoneOpt` resolve (`resolve_names`;
the Vera side's `match_constructors` adds true structural matching).
Where a language's solution uses a native
collection instead of a declared type, the native literal is emitted
instead — that is a legitimate reading of "define a linked list", not a
wrong answer.

Anything this module cannot render with confidence raises `Unsupported`,
and the caller leaves the problem ungraded with the reason recorded. A
guess here would turn a correct solution into a recorded failure.
"""

from __future__ import annotations

import json
import re

from vera_bench.vera_wrapper import Unsupported, parse_signature

#: Scalar argument types that render as plain literals in every language.
_SCALARS = frozenset({"Int", "Nat", "Bool", "String", "Float64"})


def _scalar(value: object, type_name: str, language: str) -> str:
    if type_name == "Bool":
        truthy = bool(value) if not isinstance(value, str) else value == "true"
        if language == "python":
            return "True" if truthy else "False"
        return "true" if truthy else "false"
    if type_name == "String":
        return json.dumps(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Unsupported(f"{value!r} is not a {type_name}")
    return str(value)


def _as_list(value: object, spec: dict) -> list:
    """The elements of a `form: list` value, or raise."""
    if not isinstance(value, list):
        raise Unsupported(f"{value!r} is not a list for {spec.get('type')}")
    return value


def _tagged(value: object, spec: dict) -> tuple[str, list, dict]:
    """Split a `{"Ctor": [args]}` value into (name, args, its spec entry)."""
    if not isinstance(value, dict) or len(value) != 1:
        raise Unsupported(f"{value!r} is not a single-key tagged constructor")
    name, args = next(iter(value.items()))
    if not isinstance(args, list):
        raise Unsupported(f"arguments for {name} must be a list")
    for ctor in spec.get("constructors", []):
        if ctor["name"] == name:
            if len(args) != len(ctor.get("args", [])):
                raise Unsupported(
                    f"{name} takes {len(ctor.get('args', []))} argument(s)"
                )
            return name, args, ctor
    raise Unsupported(f"unknown constructor {name!r} in test case")


def _elem_type(spec: dict) -> str:
    """The element type a `form: list` spec's cons constructor declares."""
    for ctor in spec.get("constructors", []):
        if ctor["name"] == spec.get("cons"):
            args = ctor.get("args", [])
            if args:
                return args[0]
    return "Int"


def _ctor_call(name: str, rendered: list[str], language: str) -> str:
    """Apply a constructor, respecting each language's nullary form."""
    if not rendered:
        # Python constructors are classes and must be instantiated; the
        # others name a nullary constructor bare.
        return f"{name}()" if language == "python" else name
    return f"{name}({', '.join(rendered)})"


#: A `{ tag: "Name"; field: T; field: T }` member of a TypeScript tagged
#: union — in a type alias, an interface, or a value literal. `kind` is
#: accepted alongside `tag`: it is at least as common a discriminant in
#: the wild, and a model using it is entirely correct.
_TS_TAGGED = re.compile(r"""\{\s*(tag|kind)\s*:\s*["'](\w+)["']([^}]*)\}""")
_TS_FIELD = re.compile(r"(\w+)\s*:\s*([A-Za-z_][\w\[\]<>. ]*)")


def infer_ts_discriminant(source: str) -> str:
    """The discriminant key the solution uses — `tag` unless it says `kind`.

    The constructed literals must use the solution's own key: a
    `{ tag: … }` object handed to code switching on `.kind` reads
    undefined and fails a correct solution.
    """
    m = _TS_TAGGED.search(source)
    return m.group(1) if m else "tag"


def infer_ts_fields(source: str) -> dict[str, list[tuple[str, str | None]]]:
    """(field, declared type) pairs per tag, read from the solution.

    The problem's `adt` block records canonical field names, but a model
    is free to write `{ tag: "Cons"; value: number; rest: List }` — and
    constructing arguments with the canonical `head`/`tail` against that
    declaration hands its correct code objects whose fields read as
    undefined. So names come from the source.

    Types are captured so the caller can align fields to the canonical
    argument order by type rather than position — a declaration listing
    `tail` before `head` is legal, and positional zipping would scramble
    the constructed value. A declaration-grade occurrence (every field
    carries a type-looking annotation) beats a value literal like
    `{ tag: "Cons", head: 1, … }`, whose values are not types; value
    literals contribute names with `None` types as a fallback only.
    """
    fields: dict[str, list[tuple[str, str | None]]] = {}
    typed: dict[str, bool] = {}
    for match in _TS_TAGGED.finditer(source):
        tag, body = match.group(2), match.group(3)
        pairs: list[tuple[str, str | None]] = []
        names = re.findall(r"(\w+)\s*:", body)
        types = {n: t.strip() for n, t in _TS_FIELD.findall(body)}
        is_decl = bool(names) and all(n in types for n in names)
        for n in names:
            if n in ("tag", "kind"):  # a nested literal's discriminant
                continue
            pairs.append((n, types.get(n) if is_decl else None))
        if (
            tag not in fields
            or (pairs and not fields[tag])
            or (is_decl and not typed.get(tag))
        ):
            fields[tag] = pairs
            typed[tag] = is_decl
    return fields


#: Canonical argument type -> the TypeScript type class it must land in.
_TS_CLASS = {
    "Int": "number",
    "Nat": "number",
    "Float64": "number",
    "String": "string",
    "Bool": "boolean",
}


def _fields_for(
    spec: dict,
    ctor_name: str,
    actual_tag: str,
    ts_fields: dict[str, list[tuple[str, str | None]]] | None,
) -> list[str]:
    """Field names for one constructor, ordered to match canonical args.

    A declaration may list its fields in any order — `tail` before
    `head` is legal — so the inferred fields are aligned to the
    canonical argument order by TYPE where types distinguish (a number
    field can only carry the Int argument). Fields of the same type
    keep their declared relative order, which is the only reading the
    solution's own author could have meant. Declines rather than
    guessing when the counts disagree or the alignment is not possible:
    emitting a scrambled object records a correct solution as wrong.
    """
    canonical = None
    for ctor in spec.get("constructors", []):
        if ctor["name"] == ctor_name:
            canonical = ctor.get("args", [])
            break
    if canonical is None:
        raise Unsupported(f"unknown constructor {ctor_name!r}")
    arity = len(canonical)
    if ts_fields is not None:
        inferred = ts_fields.get(actual_tag, [])
        if len(inferred) != arity:
            raise Unsupported(
                f"cannot infer TypeScript field names for {actual_tag!r} "
                f"(need {arity}, found {len(inferred)})"
            )
        if arity <= 1 or any(t is None for _, t in inferred):
            return [n for n, _ in inferred]
        remaining = list(inferred)
        ordered: list[str] = []
        for arg in canonical:
            want = _TS_CLASS.get(arg, "object")
            for idx, (n, t) in enumerate(remaining):
                have = t.strip().lower()
                if have not in _TS_CLASS.values():
                    have = "object"
                if have == want:
                    ordered.append(n)
                    del remaining[idx]
                    break
            else:
                raise Unsupported(
                    f"cannot align {actual_tag!r} fields "
                    f"{[n for n, _ in inferred]} to argument types {canonical}"
                )
        return ordered
    fields = next(
        c.get("fields", []) for c in spec["constructors"] if c["name"] == ctor_name
    )
    if len(fields) != arity:
        raise Unsupported(f"{ctor_name} has no TypeScript field names in the adt spec")
    return fields


def render(
    value: object,
    spec: dict,
    language: str,
    names: dict[str, str] | None = None,
    native: bool = False,
    qualifier: str = "",
    ts_fields: dict[str, list[tuple[str, str | None]]] | None = None,
    ts_disc: str = "tag",
) -> str:
    """Render `value` as a literal of the problem's ADT in `language`.

    `names` maps the problem's canonical constructor names onto the ones
    the solution actually declared; absent, the canonical names are used.
    `native` renders a `form: list` value as the language's own list
    literal, for solutions built on a built-in collection rather than a
    declared type (Aver's `List<Int>`).
    """
    names = names or {}

    def actual(canonical: str) -> str:
        name = names.get(canonical, canonical)
        # Aver names constructors through their type: MyList.Nil.
        return f"{qualifier}.{name}" if qualifier else name

    if spec.get("form") == "list":
        items = _as_list(value, spec)
        elem = _elem_type(spec)
        if native:
            return "[" + ", ".join(_scalar(i, elem, language) for i in items) + "]"
        if language == "typescript":
            # A tagged union all the way down, same as any other shape.
            fields = _fields_for(spec, spec["cons"], actual(spec["cons"]), ts_fields)
            out = f'{{ {ts_disc}: "{actual(spec["empty"])}" }}'
            for item in reversed(items):
                head = _scalar(item, elem, language)
                out = (
                    f'{{ {ts_disc}: "{actual(spec["cons"])}", '
                    f"{fields[0]}: {head}, {fields[1]}: {out} }}"
                )
            return out
        out = _ctor_call(actual(spec["empty"]), [], language)
        for item in reversed(items):
            out = _ctor_call(
                actual(spec["cons"]), [_scalar(item, elem, language), out], language
            )
        return out

    name, args, ctor = _tagged(value, spec)
    rendered = [
        _scalar(a, t, language)
        if t in _SCALARS
        else render(a, spec, language, names, native, qualifier, ts_fields, ts_disc)
        for a, t in zip(args, ctor["args"])
    ]
    if language == "typescript":
        # A tagged union carries named fields rather than positions.
        fields = _fields_for(spec, name, actual(name), ts_fields)
        parts = [f'{ts_disc}: "{actual(name)}"'] + [
            f"{f}: {v}" for f, v in zip(fields, rendered)
        ]
        return "{ " + ", ".join(parts) + " }"
    return _ctor_call(actual(name), rendered, language)


def render_args(
    args: list,
    param_types: list[str],
    spec: dict | None,
    language: str,
    names: dict[str, str] | None = None,
    native: bool = False,
    qualifier: str = "",
    ts_fields: dict[str, list[tuple[str, str | None]]] | None = None,
    ts_disc: str = "tag",
) -> list[str]:
    """Render a whole argument list, ADT parameters included."""
    if spec is None:
        raise Unsupported("no adt spec for this problem")
    if len(args) != len(param_types):
        # zip would silently truncate, and a wrapper calling the entry
        # point with the wrong arity records a correct solution as wrong.
        raise Unsupported(
            f"test case has {len(args)} argument(s), signature takes {len(param_types)}"
        )
    adt_type = spec.get("type")
    out = []
    for value, type_name in zip(args, param_types):
        if type_name == adt_type:
            out.append(
                render(
                    value, spec, language, names, native, qualifier, ts_fields, ts_disc
                )
            )
        elif type_name in _SCALARS:
            out.append(_scalar(value, type_name, language))
        else:
            raise Unsupported(f"cannot render a {type_name} argument")
    return out


# --- Resolving the solution's own constructor names ----------------------
# Match by name, then by NEAR-name (a unique declared name extending the
# canonical one — MyNil, NoneOpt), then decline; the mapping must also be
# one-to-one. Unlike the Vera side's match_constructors there is no
# structural fallback here: these languages' declarations do not carry
# comparable shapes cheaply, and a wrong confident mapping is the one
# outcome this module must never produce.

_DECL = {
    # Bare classes and dataclasses are the idiomatic Python ADT
    # encodings; requiring a base-class parenthesis declined them all.
    "python": re.compile(r"^class\s+(\w+)\s*[:(]", re.M),
    "typescript": re.compile(r"""\b(?:tag|kind)\s*:\s*["'](\w+)["']"""),
    "aver": re.compile(r"^\s{2,}(\w+)\s*(?:\([^)]*\))?\s*$", re.M),
    # A type may span lines: `type X =` followed by `| Ctor…` lines.
    "ailang": re.compile(r"^type\s+\w+\s*=\s*(.+(?:\n[ \t]*\|[^\n]*)*)", re.M),
}


def declared_names(source: str, language: str) -> list[str]:
    """Constructor-ish names the solution declares, best effort per language."""
    if language == "ailang":
        names: list[str] = []
        for m in _DECL["ailang"].finditer(source):
            names += re.findall(r"(\w+)", re.sub(r"\([^)]*\)", "", m.group(1)))
        return names
    if language == "aver":
        names = []
        for block in re.finditer(
            r"^type\s+\w+[ \t]*\n((?:[ \t]+\w+.*\n)+)", source, re.M
        ):
            names += re.findall(r"^\s+(\w+)", block.group(1), re.M)
        return names
    return list(dict.fromkeys(_DECL[language].findall(source)))


def uses_native_collection(source: str, spec: dict) -> bool:
    """Whether an Aver solution builds on List<Int>/Option<Int> instead.

    Reaching for the standard library is a legitimate reading of "define
    a linked list", so it is rendered as a native literal rather than
    counted against the solution.
    """
    return bool(re.search(r"\b(List|Option)<", source)) and not declared_names(
        source, "aver"
    )


def resolve_names(source: str, spec: dict, language: str) -> dict[str, str]:
    """Map canonical constructor names onto the ones the solution declares.

    A built-in carries its own constructors under the canonical names —
    Aver's `Option<Int>` is `Option.Some` / `Option.None` — so a type the
    language already provides needs no declaration to be matched.
    """
    type_name = spec.get("type", "")
    if language == "aver" and re.search(rf"\b{re.escape(type_name)}<", source):
        return {}
    declared = declared_names(source, language)
    lowered = {d.lower(): d for d in declared}
    mapping: dict[str, str] = {}
    for ctor in spec.get("constructors", []):
        want = ctor["name"]
        if want.lower() in lowered:
            mapping[want] = lowered[want.lower()]
            continue
        # A suffixed or prefixed variant of the canonical name: Python's
        # NoneOpt for None, AILANG's MyNil for Nil.
        near = [
            d
            for d in declared
            if d.lower().endswith(want.lower()) or d.lower().startswith(want.lower())
        ]
        if len(near) == 1:
            mapping[want] = near[0]
            continue
        raise Unsupported(
            f"cannot map constructor {want!r} onto {declared or 'no declaration'}"
        )
    if len(set(mapping.values())) != len(mapping):
        # Two canonical names resolved onto one declared constructor —
        # whichever call gets built is wrong for one of them, and it
        # would fail at runtime on the model's account.
        raise Unsupported(f"constructor mapping is not one-to-one: {mapping}")
    return mapping


def declared_type(source: str, language: str, spec: dict) -> str:
    """The type name an Aver solution declares, for qualified constructors.

    Aver names constructors through their type (`MyList.Nil`), so the
    renderer needs the type the solution actually declared — which need
    not be the one the problem suggested. Falls back to the built-in name
    when the solution uses `List<Int>` or `Option<Int>` instead.
    """
    if language != "aver":
        return ""
    type_name = spec.get("type", "")
    # A built-in is qualified by its own name: Option.Some.
    if re.search(rf"\b{re.escape(type_name)}<", source):
        return type_name
    wanted = {c["name"].lower() for c in spec.get("constructors", [])}
    for block in re.finditer(
        r"^type\s+(\w+)[ \t]*\n((?:[ \t]+\w+.*\n)+)", source, re.M
    ):
        ctors = {n.lower() for n in re.findall(r"^\s+(\w+)", block.group(2), re.M)}
        # The declaration whose constructors this spec actually names.
        if wanted & ctors or any(
            c.endswith(w) or w.endswith(c) for c in ctors for w in wanted
        ):
            return block.group(1)
    m = re.search(r"^type\s+(\w+)", source, re.M)
    return m.group(1) if m else ""


def return_spec(problem: dict) -> dict | None:
    """The ADT spec describing the RETURN type, if it is an ADT.

    Usually the same block as the arguments. VB-T3-010 takes a @List and
    returns an @Option, so a problem may carry `return_adt` for a second,
    different type.
    """
    spec = problem.get("return_adt") or problem.get("adt")
    if not spec:
        return None
    from vera_bench.vera_wrapper import Unsupported as _U
    from vera_bench.vera_wrapper import parse_signature

    try:
        _, ret = parse_signature(problem.get("signature", ""))
    except _U:
        return None
    return spec if ret == f"@{spec.get('type')}" else None


def returns_adt(problem: dict) -> bool:
    """Whether the entry point returns an ADT this harness can compare."""
    return return_spec(problem) is not None


def printed_form(
    value: object,
    spec: dict,
    language: str,
    names: dict[str, str] | None = None,
    native: bool = False,
    qualifier: str = "",
) -> str:
    """The string a language prints for this ADT value.

    Aver and AILANG both render a constructor application in the same
    syntax this module emits — `Cons(1, Nil)` — which makes an ADT return
    comparable without any equality instance. Aver prints a DECLARED
    type bare but keeps the qualifier on a built-in (`Option.Some(3)`),
    so the caller passes `qualifier` for a built-in and leaves it empty
    otherwise; `adt_printed` makes that call.
    """
    return render(value, spec, language, names, native, qualifier)


#: Printed between test cases by the CHECKED-IN canonical Aver/AILANG
#: mains (regenerated from the problem JSON — CLAUDE.md: "canonical
#: mains are data"), so a baseline case that prints several lines or
#: none still splits back into per-case chunks. Only the baseline path
#: uses it: the LLM evaluators run one subprocess per case, where whole
#: stdout already belongs to one case.
STDOUT_SENTINEL = "<<VB-CASE>>"


def grades_on_stdout(problem: dict) -> bool:
    """Whether this problem is graded on printed output, not a return value."""
    from vera_bench.vera_wrapper import Unsupported as _U
    from vera_bench.vera_wrapper import parse_signature

    try:
        _, ret = parse_signature(problem.get("signature", ""))
    except _U:
        return False
    return ret == "@Unit"


# --- Rendering a whole test case against one solution ---------------
# One implementation, imported by runner and baseline_runner both —
# two hand-synchronised copies of grading logic is how the wrapper
# builders drifted (#111), and these were heading the same way.


def adt_call(problem: dict, source: str, language: str, args: list) -> str | None:
    """Render an ADT call for this test case, or None when not applicable.

    Returns the arguments already rendered in the solution's own
    constructor names, e.g. `Cons(1, Nil()), 5`. None means the problem
    carries no ADT and the caller's ordinary literal path applies.
    Unsupported propagates: the problem is left ungraded rather than
    graded on a call we are not sure of.
    """
    spec = problem.get("adt")
    if not spec:
        return None
    params, _ = parse_signature(problem.get("signature", ""))
    param_types = [p.lstrip("@") for p in params]
    native = language == "aver" and uses_native_collection(source, spec)
    names = {} if native else resolve_names(source, spec, language)
    qualifier = declared_type(source, language, spec)
    ts_fields = infer_ts_fields(source) if language == "typescript" else None
    ts_disc = infer_ts_discriminant(source) if language == "typescript" else "tag"
    return ", ".join(
        render_args(
            args,
            param_types,
            spec,
            language,
            names,
            native,
            qualifier,
            ts_fields,
            ts_disc,
        )
    )


def adt_expected(
    problem: dict, source: str, language: str, expected: object
) -> str | None:
    """The expected ADT value rendered in `language`, or None.

    Only for problems whose entry point RETURNS the ADT. Both sides of
    the comparison are then built from the same constructors, so they are
    the same shape and can be compared structurally.
    """
    spec = return_spec(problem)
    if spec is None:
        return None
    native = language == "aver" and uses_native_collection(source, spec)
    names = {} if native else resolve_names(source, spec, language)
    qualifier = declared_type(source, language, spec)
    ts_fields = infer_ts_fields(source) if language == "typescript" else None
    ts_disc = infer_ts_discriminant(source) if language == "typescript" else "tag"
    return render(
        expected, spec, language, names, native, qualifier, ts_fields, ts_disc
    )


def adt_printed(
    problem: dict, source: str, language: str, expected: object
) -> str | None:
    """The expected ADT return as the language prints it, or None."""
    spec = return_spec(problem)
    if spec is None:
        return None
    native = language == "aver" and uses_native_collection(source, spec)
    names = {} if native else resolve_names(source, spec, language)
    # Aver prints a built-in qualified (`Option.Some(3)`) and a declared
    # type bare (`Cons(1, Nil)`).
    import re as _re

    type_name = spec.get("type", "")
    builtin = language == "aver" and _re.search(rf"\b{_re.escape(type_name)}<", source)
    qualifier = type_name if builtin else ""
    return printed_form(expected, spec, language, names, native, qualifier)
