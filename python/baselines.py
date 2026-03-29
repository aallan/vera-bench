# VeraBench Python Baselines
# Each function mirrors the Vera canonical solution for cross-language comparison.

# === Tier 1 ===

def absolute_value(x: int) -> int:
    if x >= 0:
        return x
    else:
        return -x

def clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    elif value > hi:
        return hi
    else:
        return value

def signum(x: int) -> int:
    if x > 0:
        return 1
    elif x < 0:
        return -1
    else:
        return 0

# === Tier 2 ===

def sum_array(arr: list[int]) -> int:
    from functools import reduce
    return reduce(lambda acc, x: acc + x, arr, 0)

def filter_positives(arr: list[int]) -> list[int]:
    return list(filter(lambda x: x > 0, arr))

def greet(name: str) -> str:
    return "Hello, " + name + "!"

# === Tier 3 ===

class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head
        self.tail = tail

def list_length(lst: List) -> int:
    match lst:
        case Nil():
            return 0
        case Cons(_, tail):
            return 1 + list_length(tail)

class Tree: pass
class Leaf(Tree):
    __match_args__ = ("value",)
    def __init__(self, value: int):
        self.value = value
class Branch(Tree):
    __match_args__ = ("left", "right")
    def __init__(self, left: 'Tree', right: 'Tree'):
        self.left = left
        self.right = right

def tree_depth(t: Tree) -> int:
    match t:
        case Leaf(_):
            return 1
        case Branch(left, right):
            return 1 + max(tree_depth(left), tree_depth(right))

class Expr: pass
class Lit(Expr):
    __match_args__ = ("value",)
    def __init__(self, value: int): self.value = value
class Add(Expr):
    __match_args__ = ("left", "right")
    def __init__(self, left: 'Expr', right: 'Expr'):
        self.left = left; self.right = right
class ExprNeg(Expr):
    __match_args__ = ("sub",)
    def __init__(self, sub: 'Expr'): self.sub = sub

def eval_expr(e: Expr) -> int:
    match e:
        case Lit(v): return v
        case Add(left, right): return eval_expr(left) + eval_expr(right)
        case ExprNeg(sub): return -eval_expr(sub)

# === Tier 4 ===

def fibonacci(n: int) -> int:
    if n == 0: return 0
    elif n == 1: return 1
    else: return fibonacci(n - 1) + fibonacci(n - 2)

def gcd(a: int, b: int) -> int:
    if b == 0: return a
    else: return gcd(b, a % b)

def is_even(n: int) -> bool:
    if n == 0: return True
    else: return is_odd(n - 1)

def is_odd(n: int) -> bool:
    if n == 0: return False
    else: return is_even(n - 1)

# === Tier 5 ===

def count_three() -> int:
    state = 0
    state = state + 1
    state = state + 1
    state = state + 1
    return state

def safe_div(a: int, b: int) -> int:
    try:
        if b == 0: raise ValueError(-1)
        return a // b
    except ValueError as e:
        return e.args[0]

# === Tests ===
if __name__ == "__main__":
    assert absolute_value(-42) == 42
    assert clamp(50, 0, 100) == 50 and clamp(-5, 0, 100) == 0 and clamp(150, 0, 100) == 100
    assert signum(42) == 1 and signum(-7) == -1 and signum(0) == 0
    assert sum_array([1,2,3,4,5]) == 15 and sum_array([]) == 0
    assert filter_positives([-1,2,-3,4,0]) == [2,4]
    assert greet("Alice") == "Hello, Alice!"
    assert list_length(Nil()) == 0 and list_length(Cons(1, Cons(2, Cons(3, Nil())))) == 3
    assert tree_depth(Leaf(1)) == 1
    assert eval_expr(Add(Lit(1), Lit(2))) == 3
    assert fibonacci(10) == 55
    assert gcd(12, 8) == 4
    assert is_even(4) is True and is_even(7) is False
    assert count_three() == 3
    assert safe_div(10, 2) == 5 and safe_div(7, 0) == -1
    print("All Python baselines pass.")
