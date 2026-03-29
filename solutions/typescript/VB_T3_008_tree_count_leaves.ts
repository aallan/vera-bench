// VB-T3-008: Tree Count Leaves -- TypeScript baseline
type Tree = { tag: "Leaf"; value: number } | { tag: "Branch"; left: Tree; right: Tree };
function treeCountLeaves(t: Tree): number {
  switch (t.tag) { case "Leaf": return 1; case "Branch": return treeCountLeaves(t.left) + treeCountLeaves(t.right); }
}
console.assert(treeCountLeaves({ tag: "Leaf", value: 1 }) === 1);
