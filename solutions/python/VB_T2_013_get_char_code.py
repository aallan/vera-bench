"""VB-T2-013: Get Char Code -- Python baseline."""
def get_char_code(s: str, index: int) -> int:
    return ord(s[index])

if __name__ == "__main__":
    assert get_char_code("A", 0) == 65
    assert get_char_code("hello", 0) == 104
    assert get_char_code("hello", 4) == 111
    assert get_char_code("Z", 0) == 90
    print("VB-T2-013 ok")
