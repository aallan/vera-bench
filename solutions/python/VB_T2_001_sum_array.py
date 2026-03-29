"""VB-T2-001: Sum Array -- Python baseline."""
from functools import reduce
def sum_array(arr: list[int]) -> int:
    return reduce(lambda acc, x: acc + x, arr, 0)

if __name__ == "__main__":
    assert sum_array([1,2,3,4,5]) == 15
    assert sum_array([]) == 0
    print("VB-T2-001 ok")
