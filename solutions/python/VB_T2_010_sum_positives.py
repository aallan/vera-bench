"""VB-T2-010: Sum Positives -- Python baseline."""
def sum_positives(arr: list[int]) -> int:
    return sum(x for x in arr if x > 0)

if __name__ == "__main__":
    assert sum_positives([-1,2,-3,4,0]) == 6
    print("VB-T2-010 ok")
