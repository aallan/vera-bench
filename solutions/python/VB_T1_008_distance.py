"""VB-T1-008: Distance -- Python baseline."""
def distance(a: int, b: int) -> int:
    return abs(a - b)

if __name__ == "__main__":
    assert distance(3, 7) == 4
    assert distance(7, 3) == 4
    assert distance(5, 5) == 0
    print("VB-T1-008 ok")
