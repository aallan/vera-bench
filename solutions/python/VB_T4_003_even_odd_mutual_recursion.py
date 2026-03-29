"""VB-T4-003: Even/Odd Mutual Recursion -- Python baseline."""
def is_even(n: int) -> bool:
    if n == 0: return True
    return is_odd(n - 1)

def is_odd(n: int) -> bool:
    if n == 0: return False
    return is_even(n - 1)

if __name__ == "__main__":
    assert is_even(4) is True
    assert is_even(7) is False
    print("VB-T4-003 ok")
