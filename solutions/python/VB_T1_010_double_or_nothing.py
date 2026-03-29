"""VB-T1-010: Double or Nothing -- Python baseline."""
def double_or_nothing(x: int) -> int:
    return x * 2 if x > 0 else 0

if __name__ == "__main__":
    assert double_or_nothing(5) == 10
    assert double_or_nothing(0) == 0
    assert double_or_nothing(-3) == 0
    print("VB-T1-010 ok")
