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
    """Split a parameter list on commas that are not inside angle brackets."""
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
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
    call = (
        f"{entry_point}("
        + ", ".join(render_value(a, t) for a, t in zip(args, params))
        + ")"
    )

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

    raise Unsupported(f"no comparison strategy for return type {ret}")


def can_wrap(signature: str) -> bool:
    """Whether this signature needs, and can have, a generated wrapper."""
    try:
        params, ret = parse_signature(signature)
    except Unsupported:
        return False
    structured = [p for p in params if p not in SCALARS]
    if not structured:
        return False  # scalars go on the command line as before
    return all(_ARRAY.match(p) for p in structured)
