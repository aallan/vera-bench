"""VB-T3-013: Classify Sign -- Python baseline."""


class Sign:
    pass


class Negative(Sign):
    pass


class Zero(Sign):
    pass


class Positive(Sign):
    pass


def classify_sign(n: int) -> int:
    s: Sign = Negative() if n < 0 else (Zero() if n == 0 else Positive())
    match s:
        case Negative():
            return -1
        case Zero():
            return 0
        case Positive():
            return 1
    return 0


if __name__ == "__main__":
    assert classify_sign(42) == 1
    assert classify_sign(-7) == -1
    assert classify_sign(0) == 0
    assert classify_sign(1) == 1
    assert classify_sign(-100) == -1
    print("VB-T3-013 ok")
