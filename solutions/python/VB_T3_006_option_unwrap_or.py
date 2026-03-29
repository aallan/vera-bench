"""VB-T3-006: Option Unwrap Or -- Python baseline."""
class Option: pass
class NoneOpt(Option): pass
class Some(Option):
    __match_args__ = ("value",)
    def __init__(self, value: int): self.value = value

def option_unwrap_or(opt: Option, default: int) -> int:
    match opt:
        case NoneOpt(): return default
        case Some(v): return v

if __name__ == "__main__":
    assert option_unwrap_or(Some(42), 0) == 42
    assert option_unwrap_or(NoneOpt(), 99) == 99
    print("VB-T3-006 ok")
