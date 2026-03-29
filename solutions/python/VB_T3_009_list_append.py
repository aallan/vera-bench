"""VB-T3-009: List Append -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

def list_append(xs: List, ys: List) -> List:
    match xs:
        case Nil(): return ys
        case Cons(head, tail): return Cons(head, list_append(tail, ys))

def to_py(lst):
    match lst:
        case Nil(): return []
        case Cons(h, t): return [h] + to_py(t)

if __name__ == "__main__":
    assert to_py(list_append(Cons(1, Cons(2, Nil())), Cons(3, Nil()))) == [1,2,3]
    print("VB-T3-009 ok")
