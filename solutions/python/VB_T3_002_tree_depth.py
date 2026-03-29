"""VB-T3-002: Tree Depth -- Python baseline."""
class Tree: pass
class Leaf(Tree):
    __match_args__ = ("value",)
    def __init__(self, value: int): self.value = value
class Branch(Tree):
    __match_args__ = ("left", "right")
    def __init__(self, left: 'Tree', right: 'Tree'):
        self.left = left; self.right = right

def tree_depth(t: Tree) -> int:
    match t:
        case Leaf(_): return 1
        case Branch(left, right): return 1 + max(tree_depth(left), tree_depth(right))

if __name__ == "__main__":
    assert tree_depth(Leaf(1)) == 1
    assert tree_depth(Branch(Leaf(1), Leaf(2))) == 2
    print("VB-T3-002 ok")
