"""VB-T4-005: Sum to N -- Python baseline."""
def sum_to_n(n: int) -> int:
    if n == 0: return 0
    return n + sum_to_n(n - 1)

if __name__ == "__main__":
    assert sum_to_n(10) == 55
    assert sum_to_n(0) == 0
    print("VB-T4-005 ok")
