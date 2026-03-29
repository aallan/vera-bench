"""VB-T1-002: Clamp -- Python baseline."""
def clamp(value: int, lo: int, hi: int) -> int:
    if value < lo: return lo
    elif value > hi: return hi
    else: return value

if __name__ == "__main__":
    assert clamp(50, 0, 100) == 50
    assert clamp(-5, 0, 100) == 0
    assert clamp(150, 0, 100) == 100
    print("VB-T1-002 ok")
