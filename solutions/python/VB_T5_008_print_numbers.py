"""VB-T5-008: Print Numbers -- Python baseline."""
def print_numbers(n: int) -> None:
    for i in range(1, n + 1):
        print(i)

if __name__ == "__main__":
    print_numbers(3)  # prints 1 2 3
    print("VB-T5-008 ok")
