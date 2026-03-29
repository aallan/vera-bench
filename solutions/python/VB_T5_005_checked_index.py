"""VB-T5-005: Checked Array Index -- Python baseline."""
def safe_index(arr: list[int], n: int) -> int:
    if n >= len(arr): return -1
    return arr[n]

if __name__ == "__main__":
    assert safe_index([10,20,30], 1) == 20
    assert safe_index([10], 5) == -1
    print("VB-T5-005 ok")
