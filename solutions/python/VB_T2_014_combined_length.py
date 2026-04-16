"""VB-T2-014: Combined String Length -- Python baseline."""
def combined_length(a: str, b: str) -> int:
    return len(a) + len(b)

if __name__ == "__main__":
    assert combined_length("hello", "world") == 10
    assert combined_length("", "") == 0
    assert combined_length("a", "bc") == 3
    assert combined_length("test", "") == 4
    print("VB-T2-014 ok")
