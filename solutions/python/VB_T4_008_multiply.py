"""VB-T4-008: Multiply -- Python baseline."""
def multiply(a: int, b: int) -> int:
    if b == 0: return 0
    return a + multiply(a, b - 1)

if __name__ == "__main__":
    assert multiply(7, 6) == 42
    assert multiply(0, 5) == 0
    print("VB-T4-008 ok")
