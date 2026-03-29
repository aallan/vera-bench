"""VB-T1-007: Safe Modulo -- Python baseline."""
def safe_modulo(a: int, b: int) -> int:
    return a % b

if __name__ == "__main__":
    assert safe_modulo(10, 3) == 1
    assert safe_modulo(6, 3) == 0
    print("VB-T1-007 ok")
