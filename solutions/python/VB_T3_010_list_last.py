"""VB-T3-010: List Last -- Python baseline."""
class List: pass
class Nil(List): pass
class Cons(List):
    __match_args__ = ("head", "tail")
    def __init__(self, head: int, tail: 'List'):
        self.head = head; self.tail = tail

class Option: pass
class NoneOpt(Option): pass
class Some(Option):
    __match_args__ = ("value",)
    def __init__(self, value: int): self.value = value

def list_last(lst: List) -> Option:
    match lst:
        case Nil(): return NoneOpt()
        case Cons(head, Nil()): return Some(head)
        case Cons(_, tail): return list_last(tail)

if __name__ == "__main__":
    assert isinstance(list_last(Nil()), NoneOpt)
    r = list_last(Cons(1, Cons(2, Cons(3, Nil()))))
    assert isinstance(r, Some) and r.value == 3
    print("VB-T3-010 ok")
