"""VB-T3-011: Safe Divide -- Python baseline."""


class Result:
    pass


class Failure(Result):
    pass


class Success(Result):
    __match_args__ = ("value",)

    def __init__(self, value: int) -> None:
        self.value = value


def safe_divide(a: int, b: int) -> int:
    r: Result = Failure() if b == 0 else Success(a // b if (a ^ b) >= 0 or a % b == 0 else a // b)
    match r:
        case Failure():
            return -1
        case Success(v):
            return v
    return -1


if __name__ == "__main__":
    assert safe_divide(10, 2) == 5
    assert safe_divide(7, 3) == 2
    assert safe_divide(10, 0) == -1
    assert safe_divide(0, 5) == 0
    assert safe_divide(-6, 3) == -2
    print("VB-T3-011 ok")
