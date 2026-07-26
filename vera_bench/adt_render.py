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

Names are matched case-insensitively and, failing that, structurally
(`match_constructors`), so a model that writes `Empty`/`Node` is graded
rather than penalised. Where a language's solution uses a native
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

from vera_bench.vera_wrapper import Unsupported

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


def _ctor_call(name: str, rendered: list[str], language: str) -> str:
    """Apply a constructor, respecting each language's nullary form."""
    if not rendered:
        # Python constructors are classes and must be instantiated; the
        # others name a nullary constructor bare.
        return f"{name}()" if language == "python" else name
    return f"{name}({', '.join(rendered)})"


def _fields_for(spec: dict, ctor_name: str) -> list[str]:
    """TypeScript field names for a constructor, or decline."""
    for ctor in spec.get("constructors", []):
        if ctor["name"] == ctor_name:
            fields = ctor.get("fields", [])
            if len(fields) != len(ctor.get("args", [])):
                raise Unsupported(
                    f"{ctor_name} has no TypeScript field names in the adt spec"
                )
            return fields
    raise Unsupported(f"unknown constructor {ctor_name!r}")


def render(
    value: object,
    spec: dict,
    language: str,
    names: dict[str, str] | None = None,
    native: bool = False,
    qualifier: str = "",
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
        if native:
            return "[" + ", ".join(_scalar(i, "Int", language) for i in items) + "]"
        if language == "typescript":
            # A tagged union all the way down, same as any other shape.
            fields = _fields_for(spec, spec["cons"])
            out = f'{{ tag: "{actual(spec["empty"])}" }}'
            for item in reversed(items):
                head = _scalar(item, "Int", language)
                out = (
                    f'{{ tag: "{actual(spec["cons"])}", '
                    f"{fields[0]}: {head}, {fields[1]}: {out} }}"
                )
            return out
        out = _ctor_call(actual(spec["empty"]), [], language)
        for item in reversed(items):
            out = _ctor_call(
                actual(spec["cons"]), [_scalar(item, "Int", language), out], language
            )
        return out

    name, args, ctor = _tagged(value, spec)
    rendered = [
        _scalar(a, t, language)
        if t in _SCALARS
        else render(a, spec, language, names, native, qualifier)
        for a, t in zip(args, ctor["args"])
    ]
    if language == "typescript":
        # A tagged union carries named fields rather than positions.
        fields = _fields_for(spec, name)
        parts = [f'tag: "{actual(name)}"'] + [
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
) -> list[str]:
    """Render a whole argument list, ADT parameters included."""
    if spec is None:
        raise Unsupported("no adt spec for this problem")
    adt_type = spec.get("type")
    out = []
    for value, type_name in zip(args, param_types):
        if type_name == adt_type:
            out.append(render(value, spec, language, names, native, qualifier))
        elif type_name in _SCALARS:
            out.append(_scalar(value, type_name, language))
        else:
            raise Unsupported(f"cannot render a {type_name} argument")
    return out


# --- Resolving the solution's own constructor names ----------------------
# Same discipline as the Vera side: match by name first, then by shape,
# then decline. A model that writes MyNil/MyCons, or Python's NoneOpt
# (because `None` is a keyword), is graded rather than penalised.

_DECL = {
    "python": re.compile(r"^class\s+(\w+)\s*\(", re.M),
    "typescript": re.compile(r'tag:\s*"(\w+)"'),
    "aver": re.compile(r"^\s{2,}(\w+)\s*(?:\([^)]*\))?\s*$", re.M),
    "ailang": re.compile(r"^type\s+\w+\s*=\s*(.+)$", re.M),
}


def declared_names(source: str, language: str) -> list[str]:
    """Constructor-ish names the solution declares, best effort per language."""
    if language == "ailang":
        m = _DECL["ailang"].search(source)
        if not m:
            return []
        return re.findall(r"(\w+)", re.sub(r"\([^)]*\)", "", m.group(1)))
    if language == "aver":
        block = re.search(r"^type\s+\w+[ \t]*\n((?:[ \t]+\w+.*\n)+)", source, re.M)
        if not block:
            return []
        return re.findall(r"^\s+(\w+)", block.group(1), re.M)
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
    """Map canonical constructor names onto the ones the solution declares."""
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
    m = re.search(r"^type\s+(\w+)", source, re.M)
    if m:
        return m.group(1)
    builtin = re.search(r"\b(List|Option)<", source)
    return builtin.group(1) if builtin else ""


def returns_adt(problem: dict) -> bool:
    """Whether the entry point returns the problem's ADT."""
    spec = problem.get("adt")
    if not spec:
        return False
    from vera_bench.vera_wrapper import Unsupported as _U
    from vera_bench.vera_wrapper import parse_signature

    try:
        _, ret = parse_signature(problem.get("signature", ""))
    except _U:
        return False
    return ret == f"@{spec.get('type')}"


def printed_form(
    value: object,
    spec: dict,
    language: str,
    names: dict[str, str] | None = None,
    native: bool = False,
) -> str:
    """The string a language prints for this ADT value.

    Aver and AILANG both render a constructor application in the same
    syntax this module emits — `Cons(1, Nil)` — which makes an ADT return
    comparable without any equality instance. Aver additionally strips
    the type qualifier it requires on the way in, so the printed form is
    the unqualified rendering.
    """
    return render(value, spec, language, names, native, qualifier="")
