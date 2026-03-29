"""VB-T4-009: List Nth -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

def list_nth(lst: List, n: int) -> int:
    match lst:
        case Nil(): return -1
        case Cons(head, tail):
            if n == 0: return head
            return list_nth(tail, n - 1)

if __name__ == "__main__":
    l = Cons(10, Cons(20, Cons(30, Nil())))
    assert list_nth(l, 0) == 10
    assert list_nth(l, 2) == 30
    assert list_nth(l, 5) == -1
    print("VB-T4-009 ok")
