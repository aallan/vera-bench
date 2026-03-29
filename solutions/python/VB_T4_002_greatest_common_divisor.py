"""VB-T4-002: Greatest Common Divisor -- Python baseline."""
def gcd(a: int, b: int) -> int:
    if b == 0: return a
    return gcd(b, a % b)

if __name__ == "__main__":
    assert gcd(12, 8) == 4
    assert gcd(7, 0) == 7
    print("VB-T4-002 ok")
