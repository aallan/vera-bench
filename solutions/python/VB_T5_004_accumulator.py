"""VB-T5-004: Accumulator -- Python baseline."""
def sum_with_state(n: int) -> int:
    state = 0
    for i in range(1, n + 1):
        state += i
    return state

if __name__ == "__main__":
    assert sum_with_state(5) == 15
    assert sum_with_state(0) == 0
    print("VB-T5-004 ok")
