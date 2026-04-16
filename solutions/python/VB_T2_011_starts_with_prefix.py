"""VB-T2-011: Starts With Prefix -- Python baseline."""
def starts_with_prefix(haystack: str, prefix: str) -> bool:
    return haystack.startswith(prefix)

if __name__ == "__main__":
    assert starts_with_prefix("hello", "hel") is True
    assert starts_with_prefix("hello", "world") is False
    assert starts_with_prefix("", "") is True
    assert starts_with_prefix("abc", "abcd") is False
    print("VB-T2-011 ok")
