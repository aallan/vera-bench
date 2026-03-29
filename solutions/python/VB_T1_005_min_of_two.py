"""VB-T1-005: Minimum of Two -- Python baseline."""
def min_of_two(a: int, b: int) -> int:
    return a if a <= b else b

if __name__ == "__main__":
    assert min_of_two(3, 7) == 3
    assert min_of_two(5, 5) == 5
    print("VB-T1-005 ok")
