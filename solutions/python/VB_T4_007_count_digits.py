"""VB-T4-007: Count Digits -- Python baseline."""
def count_digits(n: int) -> int:
    if n < 10: return 1
    return 1 + count_digits(n // 10)

if __name__ == "__main__":
    assert count_digits(0) == 1
    assert count_digits(12345) == 5
    print("VB-T4-007 ok")
