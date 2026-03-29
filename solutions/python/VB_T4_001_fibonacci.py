"""VB-T4-001: Fibonacci -- Python baseline."""
def fibonacci(n: int) -> int:
    if n == 0: return 0
    elif n == 1: return 1
    else: return fibonacci(n - 1) + fibonacci(n - 2)

if __name__ == "__main__":
    assert fibonacci(10) == 55
    assert fibonacci(0) == 0
    print("VB-T4-001 ok")
