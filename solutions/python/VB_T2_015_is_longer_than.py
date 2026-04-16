"""VB-T2-015: Is Longer Than -- Python baseline."""
def is_longer_than(s: str, threshold: int) -> bool:
    return len(s) > threshold

if __name__ == "__main__":
    assert is_longer_than("hello", 3) is True
    assert is_longer_than("hi", 5) is False
    assert is_longer_than("", 0) is False
    assert is_longer_than("test", 4) is False
    assert is_longer_than("test", 3) is True
    print("VB-T2-015 ok")
