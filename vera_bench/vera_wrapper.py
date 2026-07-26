"""Generate a Vera caller so a problem can be graded on structured input.

`vera run --fn` passes arguments on a command line, so it can only carry
scalars. That is why 24 of the 60 problems have no test cases: their entry
point takes a list, a tree or an array, and there is no way to hand one to
it. Every other language in the harness already avoids this by writing a
wrapper that calls the solution with the arguments written into the source
(see `_build_python_wrapper` and the AILANG `main` synthesis in
`runner.py`); this is Vera catching up.

Two findings from the Vera 0.1.7 compiler shape the design.

A structured return value prints as a raw memory address. `vera run` on an
entry point returning `@Array<Int>` emits something like `81972`, not the
elements. Comparing that against an expected list would compare against a
pointer, which moves with the allocator: the tests would appear to work
until they didn't. So when the return type is structured, the wrapper does
not return it. It embeds the expected value, compares in Vera, and returns
a boolean, which `vera run` prints as 1 or 0.

That comparison is exact rather than a checksum. The expected value is
known when the wrapper is generated, so the length check and the
element-by-element comparison are unrolled into the source. Vera has array
indexing (`@Array<Int>.0[i]`) but no two-array map, so an unrolled
comparison is also the only form available.

The generator declines rather than guesses. `Unsupported` means the caller
should leave the problem ungraded, exactly as today. Grading it on a
wrapper we are not sure of would turn a correct solution into a recorded
failure, which is worse than not grading it.

ADT arguments are the harder half, because the *model* defines the type.
The problem says "define a linked list ADT with Nil and Cons
constructors", so the full-spec prompt names them — but the neutral
description used for spec-from-NL only says "nil and cons", and nothing
stops a model writing `Empty` and `Node`. So a test-case value is written
against the problem's *canonical* constructor names, and the wrapper maps
those onto whatever the model actually declared:

  1. by name, case-insensitively — the overwhelmingly common case;
  2. failing that, by structure — a canonical constructor matches a model
     constructor with the same argument signature, but only when that
     signature is unique within the declaration. `Add(Expr, Expr)` and a
     hypothetical `Mul(Expr, Expr)` are indistinguishable by shape, so an
     ambiguous match declines rather than guessing wrong;
  3. failing that, decline.

That ordering matters for what a decline means. A decline is a *harness*
outcome, not a model failure: the model may well have written a perfect
solution under names we could not map. It is recorded as ungraded with a
reason, and never as a wrong answer.
"""

from __future__ import annotations

import json
import re

#: Types that survive a command line, and that `vera run` prints as values.
SCALARS = frozenset({"@Int", "@Nat", "@Bool", "@String", "@Float64"})

#: Entry point the generated wrapper exposes. Vera rejects a leading
#: underscore (`[E005] Unexpected "_"`), so this cannot be `_probe`.
PROBE_FN = "probe_main"
_EQ_FN = "probe_eq"

_SIGNATURE = re.compile(r"\(\s*(.*?)\s*->\s*([^)]+?)\s*\)\s*$")
_ARRAY = re.compile(r"^@Array<(.+)>$")


class Unsupported(Exception):
    """This signature, type or value cannot be wrapped.

    Raised rather than returning a best guess: the caller records the
    problem as ungraded, which is the honest outcome.
    """


def _split_types(text: str) -> list[str]:
    """Split on commas that are not nested inside brackets.

    Both angle brackets and parentheses count: a signature carries
    `@Map<Int, Int>` and a data declaration carries `Cons(Int, List)`,
    and splitting either down the middle silently loses a constructor.
    """
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def parse_signature(signature: str) -> tuple[list[str], str]:
    """Return (parameter types, return type) from a problem's signature.

    `public fn safe_index(@Array<Int>, @Nat -> @Int)` gives
    `(["@Array<Int>", "@Nat"], "@Int")`.
    """
    match = _SIGNATURE.search(signature.strip())
    if not match:
        raise Unsupported(f"cannot parse signature: {signature!r}")
    params = [p for p in _split_types(match.group(1)) if p and p != "@Unit"]
    return params, match.group(2).strip()


def render_value(value: object, vera_type: str) -> str:
    """Render a JSON test-case value as a Vera literal of `vera_type`."""
    array = _ARRAY.match(vera_type)
    if array:
        if not isinstance(value, list):
            raise Unsupported(f"{value!r} is not a list, cannot be {vera_type}")
        inner = array.group(1)
        return "[" + ", ".join(render_value(v, f"@{inner}") for v in value) + "]"
    if vera_type in ("@Int", "@Nat"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise Unsupported(f"{value!r} is not an integer")
        return str(value)
    if vera_type == "@Bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        if value in (0, 1):
            return "true" if value else "false"
        raise Unsupported(f"{value!r} is not a boolean")
    if vera_type == "@String":
        if not isinstance(value, str):
            raise Unsupported(f"{value!r} is not a string")
        return json.dumps(value)
    if vera_type == "@Float64":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Unsupported(f"{value!r} is not a number")
        return repr(float(value))
    raise Unsupported(f"no literal form for {vera_type}")


def entry_effects(source: str, entry_point: str) -> str:
    """The entry point's own `effects(...)` clause, or `effects(pure)`.

    Mirrored rather than assumed: a pure wrapper calling an effectful
    entry point does not compile, and the entry point's effects are the
    model's choice, not ours.
    """
    match = re.search(
        rf"\bfn\s+{re.escape(entry_point)}\s*\(.*?\)(.*?)\{{",
        source,
        re.S,
    )
    if match:
        effects = re.search(r"effects\s*\([^)]*\)", match.group(1))
        if effects:
            return effects.group(0)
    return "effects(pure)"


def _fn(
    name: str, params: str, ret: str, effects: str, body: str, *, public: bool
) -> str:
    keyword = "public" if public else "private"
    return (
        f"{keyword} fn {name}({params} -> {ret})\n"
        f"  requires(true)\n"
        f"  ensures(true)\n"
        f"  {effects}\n"
        f"{{\n{body}\n}}\n"
    )


def build_wrapper(
    source: str,
    entry_point: str,
    signature: str,
    args: list,
    expected: object,
    adt: dict | None = None,
) -> tuple[str, object]:
    """Return (wrapper source to append, expected value to compare against).

    For a scalar return the wrapper simply calls the entry point, and the
    caller compares stdout against `expected` as before. For a structured
    return the wrapper compares in Vera and returns a boolean, so the
    expected value becomes 1.
    """
    params, ret = parse_signature(signature)
    if len(args) != len(params):
        raise Unsupported(
            f"{entry_point} takes {len(params)} argument(s), test case has {len(args)}"
        )

    effects = entry_effects(source, entry_point)
    # An ADT argument is rendered with the MODEL's constructor names, so
    # the mapping is resolved once against its own declaration.
    mapping: dict[str, str] = {}
    adt_type = f"@{adt['type']}" if adt else None
    if adt is not None and adt_type in params:
        mapping = match_constructors(source, adt)

    def _arg(value: object, vera_type: str) -> str:
        if adt is not None and vera_type == adt_type:
            return render_adt(value, adt, mapping)
        return render_value(value, vera_type)

    call = f"{entry_point}(" + ", ".join(_arg(a, t) for a, t in zip(args, params)) + ")"

    if ret in SCALARS:
        body = f"  {call}"
        return _fn(PROBE_FN, "@Unit", ret, effects, body, public=True), expected

    array = _ARRAY.match(ret)
    if array:
        inner = f"@{array.group(1)}"
        if inner not in SCALARS:
            raise Unsupported(f"cannot compare an array of {inner}")
        if not isinstance(expected, list):
            raise Unsupported(f"expected {expected!r} is not a list for {ret}")
        # Unrolled: the expected value is known now, and Vera has no
        # two-array map to fold a comparison over.
        checks = (
            " && ".join(
                f"@{ret[1:]}.0[{i}] == {render_value(v, inner)}"
                for i, v in enumerate(expected)
            )
            or "true"
        )
        eq_body = (
            f"  if array_length(@{ret[1:]}.0) == {len(expected)} then {{\n"
            f"    {checks}\n"
            f"  }} else {{\n"
            f"    false\n"
            f"  }}"
        )
        eq = _fn(_EQ_FN, ret, "@Bool", "effects(pure)", eq_body, public=False)
        main = _fn(
            PROBE_FN, "@Unit", "@Bool", effects, f"  {_EQ_FN}({call})", public=True
        )
        # `vera run` prints a Bool as 1/0.
        return eq + "\n" + main, 1

    if adt is not None and ret == f"@{adt['type']}":
        if not mapping:
            mapping = match_constructors(source, adt)
        eq_body = adt_eq_body(expected, adt, mapping)
        eq = _fn(_EQ_FN, ret, "@Bool", "effects(pure)", eq_body, public=False)
        main = _fn(
            PROBE_FN, "@Unit", "@Bool", effects, f"  {_EQ_FN}({call})", public=True
        )
        return eq + "\n" + main, 1

    raise Unsupported(f"no comparison strategy for return type {ret}")


# A Vera ADT declaration: `private data List { Nil, Cons(Int, List) }`.
_DATA = re.compile(r"\bdata\s+(\w+)\s*\{(.*?)\}", re.S)
_CTOR = re.compile(r"^(\w+)\s*(?:\((.*)\))?$", re.S)

#: Stands in for the declared type inside a constructor signature, so
#: `Cons(Int, List)` and `Node(Int, Stack)` compare equal by shape.
SELF = "SELF"


def parse_data_decls(source: str) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """Every `data` declaration in the source, as {type: [(ctor, args)]}.

    Argument types are normalised so a self-reference reads as SELF,
    which is what makes structural matching work across a model's own
    choice of type name.
    """
    out: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for match in _DATA.finditer(source):
        type_name, body = match.group(1), match.group(2)
        ctors: list[tuple[str, tuple[str, ...]]] = []
        for raw in _split_types(body):
            m = _CTOR.match(raw.strip())
            if not m:
                continue
            args = tuple(
                SELF if a.strip() == type_name else a.strip()
                for a in _split_types(m.group(2) or "")
                if a.strip()
            )
            ctors.append((m.group(1), args))
        if ctors:
            out[type_name] = ctors
    return out


def _canonical_args(args: list[str], type_name: str) -> tuple[str, ...]:
    return tuple(SELF if a == type_name else a for a in args)


def match_constructors(source: str, spec: dict) -> dict[str, str]:
    """Map the problem's canonical constructor names onto the model's own.

    `spec` is the problem JSON's `adt` block: a type name and the
    constructors the problem asked for. Raises Unsupported when the
    model's declaration cannot be mapped with confidence.
    """
    type_name = spec.get("type", "")
    decls = parse_data_decls(source)
    if not decls:
        raise Unsupported("no data declaration found")
    if type_name in decls:
        model_ctors = decls[type_name]
    elif len(decls) == 1:
        # The model named the type something else. Harmless when it is
        # the only one; ambiguous when it is not.
        model_ctors = next(iter(decls.values()))
    else:
        raise Unsupported(
            f"no declaration named {type_name!r} and {len(decls)} candidates"
        )

    by_name = {name.lower(): name for name, _ in model_ctors}
    sig_count: dict[tuple[str, ...], int] = {}
    for _, args in model_ctors:
        sig_count[args] = sig_count.get(args, 0) + 1
    by_sig = {args: name for name, args in model_ctors}

    mapping: dict[str, str] = {}
    for want in spec.get("constructors", []):
        cname = want["name"]
        want_args = _canonical_args(list(want.get("args", [])), type_name)
        if cname.lower() in by_name:
            mapping[cname] = by_name[cname.lower()]
            continue
        if sig_count.get(want_args) == 1:
            mapping[cname] = by_sig[want_args]
            continue
        if want_args in sig_count:
            raise Unsupported(
                f"constructor {cname} is ambiguous: {sig_count[want_args]} "
                f"declared constructors share its shape"
            )
        raise Unsupported(f"no constructor matches {cname}{want_args or ''}")
    return mapping


def render_adt(value: object, spec: dict, mapping: dict[str, str]) -> str:
    """Render a test-case value as a Vera literal using the model's names.

    Two forms, because a linked list written in tagged form is unreadable
    past three elements and most of these problems are lists:

    - ``list``   — a JSON array, folded right onto the empty/cons pair.
    - ``tagged`` — ``{"Ctor": [arg, ...]}``, general enough for trees,
      expressions and options.
    """
    form = spec.get("form", "tagged")
    if form == "list":
        if not isinstance(value, list):
            raise Unsupported(f"{value!r} is not a list for {spec.get('type')}")
        empty, cons = spec["empty"], spec["cons"]
        out = mapping[empty]
        for item in reversed(value):
            out = f"{mapping[cons]}({render_value(item, '@Int')}, {out})"
        return out
    if not isinstance(value, dict) or len(value) != 1:
        raise Unsupported(f"{value!r} is not a single-key tagged constructor")
    ctor, args = next(iter(value.items()))
    if ctor not in mapping:
        raise Unsupported(f"unknown constructor {ctor!r} in test case")
    if not isinstance(args, list):
        raise Unsupported(f"arguments for {ctor} must be a list")
    want = next(c for c in spec["constructors"] if c["name"] == ctor)
    if len(args) != len(want.get("args", [])):
        raise Unsupported(f"{ctor} takes {len(want.get('args', []))} argument(s)")
    if not args:
        return mapping[ctor]
    rendered = [
        render_adt(a, spec, mapping)
        if t not in ("Int", "Nat", "Bool", "String", "Float64")
        else render_value(a, f"@{t}")
        for a, t in zip(args, want["args"])
    ]
    return f"{mapping[ctor]}({', '.join(rendered)})"


def adt_eq_body(expected: object, spec: dict, mapping: dict[str, str]) -> str:
    """An unrolled match that is true exactly for `expected`.

    Recursion is deliberately avoided. A generated recursive equality
    would need its own `decreases` clause and correct De Bruijn indices
    in every arm — and a wrong index there compiles, verifies, and
    computes the wrong answer, which is precisely how VB-T5-008 shipped
    broken. The expected value is known when the wrapper is generated, so
    the shape is spelled out instead: each arm either matches the exact
    constructor and payload, or returns false.

    Inside a `Cons(@Int, @List)` arm, `@Int.0` is the matched head and
    `@List.0` the matched tail — the nearest binding, not an outer one.
    """
    if spec.get("form") == "list":
        if not isinstance(expected, list):
            raise Unsupported(f"expected {expected!r} is not a list")
        empty, cons = mapping[spec["empty"]], mapping[spec["cons"]]

        def build(items: list) -> str:
            if not items:
                return (
                    f"match @List.0 {{ {empty} -> true, {cons}(@Int, @List) -> false }}"
                )
            head, rest = items[0], items[1:]
            inner = build(rest)
            return (
                f"match @List.0 {{ {empty} -> false, "
                f"{cons}(@Int, @List) -> if @Int.0 == {render_value(head, '@Int')} "
                f"then {{ {inner} }} else {{ false }} }}"
            )

        return "  " + build(expected)

    name, args, ctor = _expect_tagged(expected, spec)
    arms = []
    for c in spec.get("constructors", []):
        actual = mapping[c["name"]]
        params = ", ".join(f"@{t}" for t in c.get("args", []))
        pattern = f"{actual}({params})" if params else actual
        if c["name"] != name:
            arms.append(f"{pattern} -> false")
        elif not args:
            arms.append(f"{pattern} -> true")
        else:
            checks = " && ".join(
                f"@{t}.0 == {render_value(a, f'@{t}')}" for a, t in zip(args, c["args"])
            )
            arms.append(f"{pattern} -> {checks}")
    type_ref = f"@{spec['type']}.0"
    return f"  match {type_ref} {{ " + ", ".join(arms) + " }"


def _expect_tagged(expected: object, spec: dict) -> tuple[str, list, dict]:
    if not isinstance(expected, dict) or len(expected) != 1:
        raise Unsupported(f"expected {expected!r} is not a tagged constructor")
    name, args = next(iter(expected.items()))
    if not isinstance(args, list):
        raise Unsupported(f"arguments for {name} must be a list")
    for ctor in spec.get("constructors", []):
        if ctor["name"] == name:
            return name, args, ctor
    raise Unsupported(f"unknown constructor {name!r}")


def can_wrap(signature: str, adt: dict | None = None) -> bool:
    """Whether this signature needs, and can have, a generated wrapper.

    Scalars still go on the command line unwrapped. Arrays always wrap.
    An ADT parameter wraps only when the problem carries an `adt` spec
    to map the model's declaration onto — without one there is nothing
    to match against, and guessing is the one thing this must not do.
    """
    try:
        params, ret = parse_signature(signature)
    except Unsupported:
        return False
    structured = [p for p in params if p not in SCALARS]
    if not structured:
        return False  # scalars go on the command line as before
    return all(_ARRAY.match(p) or adt is not None for p in structured)
