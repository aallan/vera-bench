"""VB-T5-007: Exception on Negative -- Python baseline."""
def safe_non_negative(x: int) -> int:
    try:
        if x < 0: raise ValueError(x)
        return x
    except ValueError:
        return 0

if __name__ == "__main__":
    assert safe_non_negative(5) == 5
    assert safe_non_negative(-3) == 0
    assert safe_non_negative(0) == 0
    print("VB-T5-007 ok")
