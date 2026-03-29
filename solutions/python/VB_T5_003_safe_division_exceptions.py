"""VB-T5-003: Safe Division Exceptions -- Python baseline."""
def safe_div(a: int, b: int) -> int:
    try:
        if b == 0: raise ValueError(-1)
        return a // b
    except ValueError as e:
        return e.args[0]

if __name__ == "__main__":
    assert safe_div(10, 2) == 5
    assert safe_div(7, 0) == -1
    print("VB-T5-003 ok")
