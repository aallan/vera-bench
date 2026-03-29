"""VB-T5-006: State Double -- Python baseline."""
def state_double(x: int) -> int:
    state = x
    state = state * 2
    return state

if __name__ == "__main__":
    assert state_double(21) == 42
    assert state_double(0) == 0
    print("VB-T5-006 ok")
