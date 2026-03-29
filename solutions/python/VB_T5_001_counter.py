"""VB-T5-001: Counter -- Python baseline."""
def count_three() -> int:
    state = 0
    state += 1; state += 1; state += 1
    return state

if __name__ == "__main__":
    assert count_three() == 3
    print("VB-T5-001 ok")
