"""VB-T2-012: Ends With Suffix -- Python baseline."""
def ends_with_suffix(haystack: str, suffix: str) -> bool:
    return haystack.endswith(suffix)

if __name__ == "__main__":
    assert ends_with_suffix("hello", "llo") is True
    assert ends_with_suffix("hello", "world") is False
    assert ends_with_suffix("", "") is True
    assert ends_with_suffix("abc", "abcd") is False
    print("VB-T2-012 ok")
