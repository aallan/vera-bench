"""VB-T4-006: List Reverse -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

def list_reverse(lst: List) -> List:
    def go(xs, acc):
        match xs:
            case Nil(): return acc
            case Cons(h, t): return go(t, Cons(h, acc))
    return go(lst, Nil())

def to_py(lst):
    match lst:
        case Nil(): return []
        case Cons(h, t): return [h] + to_py(t)

if __name__ == "__main__":
    assert to_py(list_reverse(Cons(1, Cons(2, Cons(3, Nil()))))) == [3,2,1]
    print("VB-T4-006 ok")
