// VB-T3-002: Tree Depth -- TypeScript baseline
type Tree = { tag: "Leaf"; value: number } | { tag: "Branch"; left: Tree; right: Tree };
function treeDepth(t: Tree): number {
  switch (t.tag) { case "Leaf": return 1; case "Branch": return 1 + Math.max(treeDepth(t.left), treeDepth(t.right)); }
}
console.assert(treeDepth({ tag: "Leaf", value: 1 }) === 1);
