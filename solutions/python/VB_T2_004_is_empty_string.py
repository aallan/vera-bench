"""VB-T2-004: Is Empty String -- Python baseline."""
def is_empty_string(s: str) -> bool:
    return len(s) == 0

if __name__ == "__main__":
    assert is_empty_string("") is True
    assert is_empty_string("hi") is False
    print("VB-T2-004 ok")
