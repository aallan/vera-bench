// VB-T3-005: Tree Sum -- TypeScript baseline
type Tree = { tag: "Leaf"; value: number } | { tag: "Branch"; left: Tree; right: Tree };
function treeSum(t: Tree): number {
  switch (t.tag) { case "Leaf": return t.value; case "Branch": return treeSum(t.left) + treeSum(t.right); }
}
console.assert(treeSum({ tag: "Branch", left: { tag: "Leaf", value: 1 }, right: { tag: "Leaf", value: 2 } }) === 3);
