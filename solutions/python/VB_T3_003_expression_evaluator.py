"""VB-T3-003: Expression Evaluator -- Python baseline."""
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
        case Add(l, r): return eval_expr(l) + eval_expr(r)
        case ExprNeg(s): return -eval_expr(s)

if __name__ == "__main__":
    assert eval_expr(Add(Lit(1), Lit(2))) == 3
    assert eval_expr(ExprNeg(Lit(5))) == -5
    print("VB-T3-003 ok")
