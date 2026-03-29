"""VB-T2-002: Filter Positives -- Python baseline."""
def filter_positives(arr: list[int]) -> list[int]:
    return [x for x in arr if x > 0]

if __name__ == "__main__":
    assert filter_positives([-1,2,-3,4,0]) == [2,4]
    print("VB-T2-002 ok")
