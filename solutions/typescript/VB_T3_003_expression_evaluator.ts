// VB-T3-003: Expression Evaluator -- TypeScript baseline
type Expr = { tag: "Lit"; value: number } | { tag: "Add"; left: Expr; right: Expr } | { tag: "Neg"; sub: Expr };
function evalExpr(e: Expr): number {
  switch (e.tag) { case "Lit": return e.value; case "Add": return evalExpr(e.left) + evalExpr(e.right); case "Neg": return -evalExpr(e.sub); }
}
console.assert(evalExpr({ tag: "Add", left: { tag: "Lit", value: 1 }, right: { tag: "Lit", value: 2 } }) === 3);
