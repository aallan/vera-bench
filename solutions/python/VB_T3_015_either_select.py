"""VB-T3-015: Either Select -- Python baseline."""


class Either:
    pass


class Left(Either):
    __match_args__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value


class Right(Either):
    __match_args__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value


def either_select(a: int, b: int, selector: int) -> int:
    e: Either = Left(a) if selector > 0 else Right(b)
    match e:
        case Left(v):
            return v
        case Right(v):
            return v
    return 0


if __name__ == "__main__":
    assert either_select(10, 20, 1) == 10
    assert either_select(10, 20, 0) == 20
    assert either_select(10, 20, -5) == 20
    assert either_select(42, 99, 100) == 42
    assert either_select(0, 0, 1) == 0
    print("VB-T3-015 ok")
