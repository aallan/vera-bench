"""VB-T1-001: Absolute Value -- Python baseline."""
def absolute_value(x: int) -> int:
    return x if x >= 0 else -x

if __name__ == "__main__":
    assert absolute_value(-42) == 42
    assert absolute_value(0) == 0
    assert absolute_value(5) == 5
    print("VB-T1-001 ok")
