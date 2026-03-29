"""VB-T2-007: Double Elements -- Python baseline."""
def double_elements(arr: list[int]) -> list[int]:
    return [x * 2 for x in arr]

if __name__ == "__main__":
    assert double_elements([1,2,3]) == [2,4,6]
    print("VB-T2-007 ok")
