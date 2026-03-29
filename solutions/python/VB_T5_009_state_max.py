"""VB-T5-009: State Max -- Python baseline."""
def state_max(n: int) -> int:
    state = 0
    for i in range(1, n + 1):
        state = max(state, i)
    return state

if __name__ == "__main__":
    assert state_max(5) == 5
    assert state_max(1) == 1
    print("VB-T5-009 ok")
