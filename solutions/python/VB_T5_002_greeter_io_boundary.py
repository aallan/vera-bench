"""VB-T5-002: Greeter IO Boundary -- Python baseline."""
def build_greeting(name: str) -> str:
    return "Hello, " + name + "!\n"

def greet(name: str) -> None:
    print(build_greeting(name), end="")

if __name__ == "__main__":
    assert build_greeting("Alice") == "Hello, Alice!\n"
    print("VB-T5-002 ok")
