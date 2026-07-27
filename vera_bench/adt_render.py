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


#: Line-comment markers per language. Vera and AILANG use `--`, Aver
#: accepts both, TypeScript `//` (plus block comments), Python `#`.
_LINE_COMMENT = {
    "vera": ("--",),
    "aver": ("--", "//"),
    "ailang": ("--",),
    "typescript": ("//",),
    "python": ("#",),
}


def strip_comments(source: str, language: str) -> str:
    """Blank out comments, preserving line/column structure.

    Every declaration scanner in this harness is a regex over raw
    source, so a comment is indistinguishable from code to them. That is
    not academic: a comment inside a Vera `data` block drops a
    constructor, a commented-out canonical declaration shadows the
    model's real one, a doc comment mentioning `List<Int>` flips an Aver
    solution onto nonexistent builtin members, and a JSDoc `@example`
    overrides a TypeScript declaration's field names — each recording a
    correct solution as a wrong answer.

    Comment bodies are replaced with spaces rather than removed so that
    any offset a caller derives still lines up. String literals are
    honoured: a `--` or `//` inside a string is code, not a comment.
    """
    markers = _LINE_COMMENT.get(language, ("--", "//", "#"))
    out = []
    in_str: str | None = None
    block = False
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if block:
            if source.startswith("*/", i):
                out.append("  ")
                i += 2
                block = False
            else:
                out.append(" " if ch != "\n" else "\n")
                i += 1
            continue
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "\"'":
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if language == "typescript" and source.startswith("/*", i):
            out.append("  ")
            i += 2
            block = True
            continue
        if any(source.startswith(m, i) for m in markers):
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


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


def _dataclass_aliases(tree: object) -> set[str]:
    """Module-scope names that actually refer to dataclasses.dataclass.

    Only top-level bindings count, and a later top-level rebinding
    removes one: an import nested inside a function does not authorise a
    module-level decorator of the same name, and a module-level `def dc`
    shadowing an earlier import means `@dc(...)` is not a dataclass at
    all. Getting this wrong builds a positional constructor by keyword.
    """
    import ast

    names = set()
    body = getattr(tree, "body", [])
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module == "dataclasses":
            for a in node.names:
                if a.name == "dataclass":
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "dataclasses":
                    names.add((a.asname or a.name) + ".dataclass")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.discard(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.discard(t.id)
    return names


def _is_dataclass_decorator(func: object, aliases: set[str]) -> bool:
    """Whether a decorator expression resolves to dataclasses.dataclass.

    An unrelated decorator that happens to take a `kw_only` keyword would
    otherwise be read as one, and the constructor built by keyword
    against a positional signature.
    """
    import ast

    if isinstance(func, ast.Name):
        return func.id in aliases
    if isinstance(func, ast.Attribute):
        return ast.unparse(func) in aliases
    return False


def python_kwonly_fields(source: str) -> dict[str, list[str]]:
    """Keyword-only parameter names per class, for kw_only dataclasses.

    `@dataclass(kw_only=True)` is legal Python 3.10+ and nothing in the
    prompt forbids it, but a positional `Cons(1, Nil())` raises
    TypeError against it — a correct solution graded wrong. Where the
    constructor is keyword-only we emit keyword form using the
    solution's OWN names.
    """
    import ast

    out: dict[str, list[str]] = {}
    try:
        tree = ast.parse(strip_comments(source, "python"))
    except SyntaxError:
        return out
    aliases = _dataclass_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        init = next(
            (
                n
                for n in node.body
                if isinstance(n, ast.FunctionDef) and n.name == "__init__"
            ),
            None,
        )
        if init is not None:
            if init.args.kwonlyargs and len(init.args.args) <= 1:
                out[node.name] = [a.arg for a in init.args.kwonlyargs]
            continue
        kw_only = any(
            isinstance(d, ast.Call)
            and _is_dataclass_decorator(d.func, aliases)
            and any(
                k.arg == "kw_only" and getattr(k.value, "value", False) is True
                for k in d.keywords
            )
            for d in node.decorator_list
        )
        if kw_only:
            # `obj.attr: int` is a legal annotated assignment whose
            # target is an Attribute, not a Name — reading .id crashed.
            out[node.name] = [
                n.target.id
                for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            ]
    return out


def _type_mismatch(declared: str, wanted: str) -> bool:
    """Whether two normalised types genuinely disagree.

    Module-level so `resolve_names` and `align_kwonly` cannot drift
    apart: a solution whose `head: str` satisfied the shape guard used
    to fail the alignment loop's raw `==` and decline anyway. An
    unrecognised type name is UNVERIFIABLE everywhere rather than a
    mismatch — comparing raw tokens would false-decline a solution whose
    type names we simply cannot interpret.
    """
    if declared == wanted:
        return False
    if "SELF" in (declared, wanted):
        return True
    dk, wk = _SCALAR_EQUIV.get(declared), _SCALAR_EQUIV.get(wanted)
    return bool(dk and wk and dk != wk)


def align_kwonly(
    fields: dict[str, list[str]],
    source: str,
    spec: dict,
    names: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Reorder keyword-only field names into CANONICAL argument order.

    `rendered` values are built in the spec's argument order while the
    names come from the declaration, so zipping them directly bound each
    value to the wrong field — `Cons(tail=1, head=Nil())` — which is a
    mis-grade, strictly worse than the false decline this ordering
    tolerance replaced. Fields are matched to arguments by declared
    type, exactly as the TypeScript path aligns its own.

    A constructor that cannot be aligned raises `Unsupported`, leaving
    the problem ungraded. It is deliberately NOT dropped: dropping falls
    back to positional rendering, which a keyword-only class rejects
    with `TypeError` — published as the model's wrong answer. Where
    types are unreadable the canonical field names are used instead,
    when they biject with the declared ones, so that case is still
    graded rather than declined.
    """
    shapes = declared_shape(source, "python")
    type_name = spec.get("type", "")
    names = names or {}
    out: dict[str, list[str]] = {}
    for ctor in spec.get("constructors", []):
        # Only the class this constructor actually resolved to. Scanning
        # every keyword-only class meant an unrelated helper dataclass
        # of the same arity hit the ambiguity branch and declined the
        # whole problem.
        actual = names.get(ctor["name"], ctor["name"])
        if actual in fields:
            field_names = fields[actual]
            declared = shapes.get(actual)
            canonical = ctor.get("fields", [])
            if declared is None or len(declared) != len(field_names):
                # A keyword-only constructor must NEVER fall through to
                # positional rendering — that is a TypeError published as
                # the model's wrong answer. Types are unavailable here
                # (an unannotated keyword-only __init__, say), so the
                # canonical names are the only way to order the fields:
                # use them when they biject, and decline otherwise.
                if canonical and set(canonical) == set(field_names):
                    out[actual] = list(canonical)
                elif not field_names and not canonical:
                    out[actual] = []
                else:
                    raise Unsupported(
                        f"cannot align keyword-only fields {field_names} for "
                        f"{actual}: no readable argument types and the "
                        f"declared names do not match {canonical}"
                    )
                continue
            wanted = [
                "SELF" if a.lower() == type_name.lower() else a.lower()
                for a in ctor.get("args", [])
            ]
            if len(wanted) != len(field_names):
                # Arity disagreement on a keyword-only constructor: a
                # genuine mismatch, and again never a positional
                # fallback.
                raise Unsupported(
                    f"constructor {ctor['name']} declares {len(field_names)} "
                    f"keyword-only field(s), expected {len(wanted)}"
                )
            canonical_fields = canonical
            if len(set(wanted)) != len(wanted):
                # Two arguments share a type — `Branch(Tree, Tree)` — so
                # types cannot say which declared field is which, and
                # declaration order is not a proxy for semantic order
                # once reordering is allowed. Names can still resolve it
                # when the solution used the canonical ones; otherwise
                # decline, because guessing reverses the children
                # silently.
                if canonical_fields and set(canonical_fields) == set(field_names):
                    out[actual] = list(canonical_fields)
                    continue
                raise Unsupported(
                    f"cannot align keyword-only fields {field_names} for "
                    f"{actual}: {len(wanted)} arguments share a type and "
                    f"the declared names do not match {canonical_fields}"
                )
            remaining = list(zip(field_names, declared))
            ordered: list[str] = []
            for want in wanted:
                match = next(
                    (
                        i
                        for i, (_, t) in enumerate(remaining)
                        if not _type_mismatch(t, want)
                    ),
                    None,
                )
                if match is None:
                    ordered = []
                    break
                ordered.append(remaining.pop(match)[0])
            if not ordered and wanted:
                # A keyword-only constructor we cannot order must not
                # fall back to positional — that raises TypeError and is
                # published as the model's wrong answer.
                raise Unsupported(
                    f"cannot align keyword-only fields {field_names} for {actual}"
                )
            out[actual] = ordered
    # Nullary constructors carry no fields and need no alignment.
    for actual, field_names in fields.items():
        if not field_names:
            out.setdefault(actual, [])
    return out


def _ctor_call(
    name: str,
    rendered: list[str],
    language: str,
    kwargs: list[str] | None = None,
) -> str:
    """Apply a constructor, respecting each language's nullary form."""
    if not rendered:
        # Python constructors are classes and must be instantiated; the
        # others name a nullary constructor bare.
        return f"{name}()" if language == "python" else name
    if kwargs and len(kwargs) == len(rendered):
        return f"{name}({', '.join(f'{k}={v}' for k, v in zip(kwargs, rendered))})"
    return f"{name}({', '.join(rendered)})"


#: A `{ tag: "Name"; field: T; field: T }` member of a TypeScript tagged
#: union — in a type alias, an interface, or a value literal. `kind` is
#: accepted alongside `tag`: it is at least as common a discriminant in
#: the wild, and a model using it is entirely correct.
_TS_BLOCK = re.compile(r"\{([^{}]*)\}")
_TS_DISC = re.compile(r"""\b(?:readonly\s+)?(tag|kind)\s*:\s*["'](\w+)["']""")
_TS_FIELD = re.compile(r"\b(?:readonly\s+)?(\w+)\s*:\s*([A-Za-z_][\w\[\]<>. ]*)")


_TS_DECL_START = re.compile(r"\b(type|interface)\s+\w+")


def _ts_declaration_regions(source: str) -> list[str]:
    """The type/interface declarations in a TypeScript source.

    Scanned with brace depth rather than matched by regex: `;` is also
    the field separator INSIDE a union member, so a pattern ending at
    the first semicolon truncated `type List = { tag: "Cons";` — no
    complete block remained in the region, inference fell through to the
    whole-source scan, and an object literal could pick the discriminant
    again. That is the very failure the declaration-first rule exists to
    prevent.

    A `type` runs to its terminating semicolon at depth 0 (or to the end
    of the source); an `interface` runs to its closing brace.
    """
    regions: list[str] = []
    for m in _TS_DECL_START.finditer(source):
        kind, i, depth, started = m.group(1), m.end(), 0, False
        while i < len(source):
            ch = source[i]
            if ch in "{([":
                depth += 1
                started = True
            elif ch in "})]":
                depth -= 1
                if kind == "interface" and started and depth == 0:
                    i += 1
                    break
            elif ch == ";" and depth == 0:
                i += 1
                break
            i += 1
        regions.append(source[m.start() : i])
    return regions


def infer_ts_discriminant(source: str) -> str:
    """The discriminant key the solution uses — `tag` unless it says `kind`.

    The constructed literals must use the solution's own key: a
    `{ tag: … }` object handed to code switching on `.kind` reads
    undefined and fails a correct solution.
    """
    src = strip_comments(source, "typescript")
    # A `type`/`interface` declaration outranks any object literal: a
    # seed constant or example value written before the declaration
    # would otherwise pick the discriminant, and the wrapper would build
    # `{ kind: … }` objects against a `tag` union — the solution's own
    # switch then reads undefined and a correct answer grades 0.
    for region in _ts_declaration_regions(src):
        for block in _TS_BLOCK.finditer(region):
            disc = _TS_DISC.search(block.group(1))
            if disc:
                return disc.group(1)
    for block in _TS_BLOCK.finditer(src):
        disc = _TS_DISC.search(block.group(1))
        if disc:
            return disc.group(1)
    return "tag"


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
    source = strip_comments(source, "typescript")
    fields: dict[str, list[tuple[str, str | None]]] = {}
    typed: dict[str, bool] = {}
    for block in _TS_BLOCK.finditer(source):
        body = block.group(1)
        disc = _TS_DISC.search(body)
        if not disc:
            continue
        tag = disc.group(2)
        # The discriminant may sit anywhere in the block and may be
        # `readonly` — an idiomatic declaration that used to be
        # invisible, ungrading every correct solution written that way.
        pairs: list[tuple[str, str | None]] = []
        # The discriminant is excluded before judging whether this block
        # is a DECLARATION: its value is a string literal, never a type,
        # so counting it would make every declaration look untyped and
        # silently disable type-based field alignment.
        # Only the key this block actually discriminates on is dropped:
        # excluding both spellings deleted a payload field legitimately
        # named `kind` under a `tag` union, leaving the constructor an
        # argument short.
        names = [
            n
            for n in re.findall(r"\b(?:readonly\s+)?(\w+)\s*:", body)
            if n != disc.group(1)
        ]
        types = {n: t.strip() for n, t in _TS_FIELD.findall(body)}
        is_decl = bool(names) and all(n in types for n in names)
        for n in names:
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
    py_kwonly: dict[str, list[str]] | None = None,
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
                actual(spec["cons"]),
                [_scalar(item, elem, language), out],
                language,
                (py_kwonly or {}).get(actual(spec["cons"])),
            )
        return out

    name, args, ctor = _tagged(value, spec)
    rendered = [
        _scalar(a, t, language)
        if t in _SCALARS
        else render(
            a, spec, language, names, native, qualifier, ts_fields, ts_disc, py_kwonly
        )
        for a, t in zip(args, ctor["args"])
    ]
    if language == "typescript":
        # A tagged union carries named fields rather than positions.
        fields = _fields_for(spec, name, actual(name), ts_fields)
        parts = [f'{ts_disc}: "{actual(name)}"'] + [
            f"{f}: {v}" for f, v in zip(fields, rendered)
        ]
        return "{ " + ", ".join(parts) + " }"
    return _ctor_call(
        actual(name), rendered, language, (py_kwonly or {}).get(actual(name))
    )


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
    py_kwonly: dict[str, list[str]] | None = None,
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
                    value,
                    spec,
                    language,
                    names,
                    native,
                    qualifier,
                    ts_fields,
                    ts_disc,
                    py_kwonly,
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
    # `type MyList[a] = …` is the generic form AILANG's own prompt
    # teaches; the parameter list used to block the match entirely.
    "ailang": re.compile(
        r"^type\s+\w+\s*(?:\[[^\]]*\])?\s*=\s*(.+(?:\n[ \t]*\|[^\n]*)*)", re.M
    ),
}


#: Each language's spelling of the same scalar, mapped to one token, so
#: a declared shape can be compared with the spec's for EQUALITY rather
#: than only for self-reference. Without this, `Cons(String, Self)`
#: against a canonical `Cons(Int, Self)` passed validation and the
#: wrapper rendered an integer into a string field.
_SCALAR_EQUIV = {
    "int": "int",
    "nat": "int",
    "integer": "int",
    "number": "int",
    "str": "string",
    "string": "string",
    "bool": "bool",
    "boolean": "bool",
    "float": "float",
    "float64": "float",
    "double": "float",
}


def declared_shape(source: str, language: str) -> dict[str, tuple[str, ...]]:
    """Declared constructor argument SHAPES, where the language shows them.

    Arity alone cannot catch the case that matters: `Cons(List, Int)` is
    a swap, not a count mismatch, and rendering the canonical order into
    it produces a call that fails at runtime — recorded as the model's
    wrong answer. Types are normalised so a self-reference reads as SELF
    and scalars compare case-insensitively, letting a spec's
    `["Int", "List"]` be compared with what the solution actually wrote.

    A constructor absent from the result is UNVERIFIABLE, not nullary —
    Python without annotations, for instance. Callers must not treat a
    missing entry as a mismatch.
    """
    src = strip_comments(source, language)
    out: dict[str, tuple[str, ...]] = {}

    def norm(t: str, self_names: object) -> str:
        if isinstance(self_names, str):
            self_names = {self_names}
        t = t.strip().split(":")[-1].strip().rstrip(",")
        t = re.sub(r"\[[^\]]*\]", "", t).strip()
        lowered = {n.lower() for n in self_names}
        return "SELF" if t.lower() in lowered else t.lower()

    if language in ("aver", "ailang"):
        for decl in re.finditer(r"\btype\s+(\w+)", src):
            self_name = decl.group(1)
            body = src[decl.end() :]
            nxt = re.search(r"\btype\s+\w+", body)
            if nxt:
                body = body[: nxt.start()]
            for name, args in re.findall(r"\b(\w+)\s*\(([^)]*)\)", body):
                # `[^)]*` cannot see a nested application, and splitting
                # on commas would flatten it into the wrong arity.
                # Unverifiable beats wrong: leave it out and the shape
                # guard skips this constructor.
                if "(" in args:
                    continue
                parts = [a for a in args.split(",") if a.strip()]
                out.setdefault(name, tuple(norm(a, self_name) for a in parts))
    if language == "python":
        import ast

        try:
            tree = ast.parse(src)
        except SyntaxError:
            return {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            init = next(
                (
                    n
                    for n in node.body
                    if isinstance(n, ast.FunctionDef) and n.name == "__init__"
                ),
                None,
            )
            # A Python ADT's recursive reference is the BASE class
            # (`tail: List`), not the constructor's own class.
            selfish = {node.name} | {
                b.id for b in node.bases if isinstance(b, ast.Name)
            }
            if init is not None:
                # The instance parameter is the first POSITIONAL one,
                # which lands in posonlyargs for `def __init__(self, /,
                # *, ...)` — a legal signature whose `self` used to be
                # read as an extra argument, giving the constructor one
                # too many and declining a correct solution.
                positional = init.args.posonlyargs + init.args.args
                params = positional[1:] + init.args.kwonlyargs
                if all(p.annotation is not None for p in params) and params:
                    out[node.name] = tuple(
                        norm(ast.unparse(p.annotation).strip("\"'"), selfish)
                        for p in params
                    )
            else:
                fields = [n for n in node.body if isinstance(n, ast.AnnAssign)]
                if fields:
                    out[node.name] = tuple(
                        norm(ast.unparse(f.annotation).strip("\"'"), selfish)
                        for f in fields
                    )
    return out


def declared_names(source: str, language: str) -> list[str]:
    """Constructor-ish names the solution declares, best effort per language."""
    source = strip_comments(source, language)
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
    # Per-TYPE, and comment-blind no longer: a doc comment merely
    # mentioning List<Int>, or an unrelated declared type elsewhere in
    # the file, used to flip a correct solution onto builtin members
    # that do not exist.
    src = strip_comments(source, "aver")
    type_name = spec.get("type", "")
    if not re.search(rf"\b{re.escape(type_name)}<", src):
        return False
    wanted = {c["name"].lower() for c in spec.get("constructors", [])}
    declared = {n.lower() for n in declared_names(src, "aver")}
    return not (wanted <= declared)


def _uses_ailang_prelude(source: str, spec: dict) -> bool:
    """Whether an AILANG solution leans on a prelude type it never declares."""
    names = [c["name"] for c in spec.get("constructors", [])]
    if not names:
        return False
    declared = {n.lower() for n in declared_names(source, "ailang")}
    if any(n.lower() in declared for n in names):
        return False
    return all(re.search(rf"\b{re.escape(n)}\b", source) for n in names)


def resolve_names(source: str, spec: dict, language: str) -> dict[str, str]:
    """Map canonical constructor names onto the ones the solution declares.

    A built-in carries its own constructors under the canonical names —
    Aver's `Option<Int>` is `Option.Some` / `Option.None` — so a type the
    language already provides needs no declaration to be matched.
    """
    type_name = spec.get("type", "")
    source = strip_comments(source, language)
    if language == "aver" and re.search(rf"\b{re.escape(type_name)}<", source):
        return {}
    if language == "ailang" and _uses_ailang_prelude(source, spec):
        # Option/Some/None come from the auto-imported prelude, so there
        # is no declaration to match — the canonical names ARE the
        # prelude's, and a correct solution using them used to decline.
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
    # Shape validation, the guard the Vera side has had since #112: a
    # solution declaring Cons(List, Int) — swapped but internally
    # consistent and spec-legal — was rendered against the canonical
    # order and graded WRONG. A mapping we cannot build a correct call
    # for is a decline, not the model's failure.
    shapes = declared_shape(source, language)
    kwonly = python_kwonly_fields(source) if language == "python" else {}
    type_name = spec.get("type", "")

    for want in spec.get("constructors", []):
        actual = mapping.get(want["name"])
        declared = shapes.get(actual)
        if declared is None:
            continue  # unverifiable in this language, not a mismatch
        if actual in kwonly:
            # A keyword-only constructor is built by NAME, so the order
            # it declares its fields in carries no meaning — comparing
            # positionally would decline a correct solution that simply
            # listed them differently. Compare as multisets: a genuine
            # arity or type mismatch is still caught.
            def _key(t: str) -> str:
                return "SELF" if t == "SELF" else _SCALAR_EQUIV.get(t, t)

            wanted_sorted = sorted(
                _key("SELF" if a.lower() == type_name.lower() else a.lower())
                for a in want.get("args", [])
            )
            declared_sorted = sorted(_key(d) for d in declared)
            if len(declared_sorted) != len(wanted_sorted) or any(
                _type_mismatch(d, w) for d, w in zip(declared_sorted, wanted_sorted)
            ):
                raise Unsupported(
                    f"constructor {want['name']} is declared as {declared}, "
                    f"expected {tuple(wanted_sorted)} in some order"
                )
            continue
        wanted = tuple(
            "SELF" if a.lower() == type_name.lower() else a.lower()
            for a in want.get("args", [])
        )

        if len(declared) != len(wanted) or any(
            _type_mismatch(d, w) for d, w in zip(declared, wanted)
        ):
            raise Unsupported(
                f"constructor {want['name']} is declared as {declared}, "
                f"expected {wanted}"
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
    py_kwonly = (
        align_kwonly(python_kwonly_fields(source), source, spec, names)
        if language == "python"
        else None
    )
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
            py_kwonly,
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
    py_kwonly = (
        align_kwonly(python_kwonly_fields(source), source, spec, names)
        if language == "python"
        else None
    )
    return render(
        expected,
        spec,
        language,
        names,
        native,
        qualifier,
        ts_fields,
        ts_disc,
        py_kwonly,
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
