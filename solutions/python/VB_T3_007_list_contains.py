"""VB-T3-007: List Contains -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

def list_contains(lst: List, target: int) -> bool:
    match lst:
        case Nil(): return False
        case Cons(head, tail): return head == target or list_contains(tail, target)

if __name__ == "__main__":
    assert list_contains(Cons(1, Cons(2, Cons(3, Nil()))), 2) is True
    assert list_contains(Cons(1, Nil()), 5) is False
    print("VB-T3-007 ok")
