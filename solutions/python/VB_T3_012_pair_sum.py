"""VB-T3-012: Pair Sum -- Python baseline."""


class Pair:
    pass


class MkPair(Pair):
    __match_args__ = ("first", "second")

    def __init__(self, first: int, second: int) -> None:
        self.first = first
        self.second = second


def pair_sum(a: int, b: int) -> int:
    p = MkPair(a, b)
    match p:
        case MkPair(x, y):
            return x + y
    return 0


if __name__ == "__main__":
    assert pair_sum(3, 4) == 7
    assert pair_sum(0, 0) == 0
    assert pair_sum(-5, 5) == 0
    assert pair_sum(10, -3) == 7
    assert pair_sum(100, 200) == 300
    print("VB-T3-012 ok")
