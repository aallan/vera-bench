// VB-T3-001: List Length -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
function listLength(lst: List): number {
  switch (lst.tag) { case "Nil": return 0; case "Cons": return 1 + listLength(lst.tail); }
}
console.assert(listLength({ tag: "Nil" }) === 0);
