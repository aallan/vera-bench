// VB-T4-009: List Nth -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
function listNth(lst: List, n: number): number {
  switch (lst.tag) { case "Nil": return -1; case "Cons": return n === 0 ? lst.head : listNth(lst.tail, n - 1); }
}
