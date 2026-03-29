"""VB-T3-004: List Sum -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

def list_sum(lst: List) -> int:
    match lst:
        case Nil(): return 0
        case Cons(head, tail): return head + list_sum(tail)

if __name__ == "__main__":
    assert list_sum(Nil()) == 0
    assert list_sum(Cons(1, Cons(2, Cons(3, Nil())))) == 6
    print("VB-T3-004 ok")
