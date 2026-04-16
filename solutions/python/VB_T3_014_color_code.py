"""VB-T3-014: Color to RGB Code -- Python baseline."""


class Color:
    pass


class Red(Color):
    pass


class Green(Color):
    pass


class Blue(Color):
    pass


class Black(Color):
    pass


def color_code(code: int) -> int:
    c: Color
    if code == 0:
        c = Red()
    elif code == 1:
        c = Green()
    elif code == 2:
        c = Blue()
    else:
        c = Black()
    match c:
        case Red():
            return 16711680
        case Green():
            return 65280
        case Blue():
            return 255
        case Black():
            return 0
    return 0


if __name__ == "__main__":
    assert color_code(0) == 16711680
    assert color_code(1) == 65280
    assert color_code(2) == 255
    assert color_code(3) == 0
    assert color_code(-1) == 0
    print("VB-T3-014 ok")
