"""VB-T5-010: Safe Head -- Python baseline."""
def safe_head(arr: list[int]) -> int:
    if len(arr) == 0: return -1
    return arr[0]

if __name__ == "__main__":
    assert safe_head([10,20]) == 10
    assert safe_head([]) == -1
    print("VB-T5-010 ok")
