"""VB-T1-006: Is Positive -- Python baseline."""
def is_positive(x: int) -> bool:
    return x > 0

if __name__ == "__main__":
    assert is_positive(5) is True
    assert is_positive(-3) is False
    assert is_positive(0) is False
    print("VB-T1-006 ok")
