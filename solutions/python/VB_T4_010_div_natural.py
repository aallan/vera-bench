"""VB-T4-010: Natural Division -- Python baseline."""
def div_natural(a: int, b: int) -> int:
    if a < b: return 0
    return 1 + div_natural(a - b, b)

if __name__ == "__main__":
    assert div_natural(17, 5) == 3
    assert div_natural(10, 3) == 3
    assert div_natural(0, 1) == 0
    print("VB-T4-010 ok")
