"""VB-T3-008: Tree Count Leaves -- Python baseline."""
class Tree: pass
class Leaf(Tree):
    __match_args__ = ("value",)
    def __init__(self, value: int): self.value = value
class Branch(Tree):
    __match_args__ = ("left", "right")
    def __init__(self, left: 'Tree', right: 'Tree'):
        self.left = left; self.right = right

def tree_count_leaves(t: Tree) -> int:
    match t:
        case Leaf(_): return 1
        case Branch(l, r): return tree_count_leaves(l) + tree_count_leaves(r)

if __name__ == "__main__":
    assert tree_count_leaves(Leaf(1)) == 1
    assert tree_count_leaves(Branch(Leaf(1), Branch(Leaf(2), Leaf(3)))) == 3
    print("VB-T3-008 ok")
