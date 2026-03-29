"""VB-T2-005: Contains Substring -- Python baseline."""
def contains_substring(haystack: str, needle: str) -> bool:
    return needle in haystack

if __name__ == "__main__":
    assert contains_substring("hello world", "world") is True
    assert contains_substring("hello", "xyz") is False
    print("VB-T2-005 ok")
