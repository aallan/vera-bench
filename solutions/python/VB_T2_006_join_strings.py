"""VB-T2-006: Join Strings -- Python baseline."""
def join_strings(arr: list[str], sep: str) -> str:
    return sep.join(arr)

if __name__ == "__main__":
    assert join_strings(["a","b","c"], ",") == "a,b,c"
    print("VB-T2-006 ok")
