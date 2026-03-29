"""VB-T2-009: To Upper Case -- Python baseline."""
def to_upper(s: str) -> str:
    return s.upper()

if __name__ == "__main__":
    assert to_upper("hello") == "HELLO"
    print("VB-T2-009 ok")
