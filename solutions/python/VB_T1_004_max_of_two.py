"""VB-T1-004: Maximum of Two -- Python baseline."""
def max_of_two(a: int, b: int) -> int:
    return a if a >= b else b

if __name__ == "__main__":
    assert max_of_two(3, 7) == 7
    assert max_of_two(5, 5) == 5
    print("VB-T1-004 ok")
