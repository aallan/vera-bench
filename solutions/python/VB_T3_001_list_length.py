"""VB-T3-001: List Length -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

def list_length(lst: List) -> int:
    match lst:
        case Nil(): return 0
        case Cons(_, tail): return 1 + list_length(tail)

if __name__ == "__main__":
    assert list_length(Nil()) == 0
    assert list_length(Cons(1, Cons(2, Cons(3, Nil())))) == 3
    print("VB-T3-001 ok")
