"""VB-T1-009: Maximum of Three -- Python baseline."""
def max_of_three(a: int, b: int, c: int) -> int:
    if a >= b and a >= c: return a
    elif b >= c: return b
    else: return c

if __name__ == "__main__":
    assert max_of_three(3, 7, 5) == 7
    assert max_of_three(9, 1, 4) == 9
    assert max_of_three(2, 2, 8) == 8
    print("VB-T1-009 ok")
