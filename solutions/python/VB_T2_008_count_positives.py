"""VB-T2-008: Count Positives -- Python baseline."""
def count_positives(arr: list[int]) -> int:
    return len([x for x in arr if x > 0])

if __name__ == "__main__":
    assert count_positives([-1,2,-3,4,0]) == 2
    print("VB-T2-008 ok")
