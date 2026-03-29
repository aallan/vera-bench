"""VB-T1-003: Signum -- Python baseline."""
def signum(x: int) -> int:
    if x > 0: return 1
    elif x < 0: return -1
    else: return 0

if __name__ == "__main__":
    assert signum(42) == 1
    assert signum(-7) == -1
    assert signum(0) == 0
    print("VB-T1-003 ok")
