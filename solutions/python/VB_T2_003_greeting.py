"""VB-T2-003: Greeting -- Python baseline."""
def greet(name: str) -> str:
    return "Hello, " + name + "!"

if __name__ == "__main__":
    assert greet("Alice") == "Hello, Alice!"
    print("VB-T2-003 ok")
