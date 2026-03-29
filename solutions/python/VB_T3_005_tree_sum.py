"""VB-T3-005: Tree Sum -- Python baseline."""
class Tree: pass
class Leaf(Tree):
    __match_args__ = ("value",)
    def __init__(self, value: int): self.value = value
class Branch(Tree):
    __match_args__ = ("left", "right")
    def __init__(self, left: 'Tree', right: 'Tree'):
        self.left = left; self.right = right

def tree_sum(t: Tree) -> int:
    match t:
        case Leaf(v): return v
        case Branch(l, r): return tree_sum(l) + tree_sum(r)

if __name__ == "__main__":
    assert tree_sum(Leaf(5)) == 5
    assert tree_sum(Branch(Leaf(1), Leaf(2))) == 3
    print("VB-T3-005 ok")
