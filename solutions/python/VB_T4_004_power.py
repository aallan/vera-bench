"""VB-T4-004: Power -- Python baseline."""
def power(base: int, exp: int) -> int:
    if exp == 0: return 1
    return base * power(base, exp - 1)

if __name__ == "__main__":
    assert power(2, 10) == 1024
    assert power(3, 0) == 1
    print("VB-T4-004 ok")
