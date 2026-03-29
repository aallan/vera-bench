// VB-T3-007: List Contains -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
function listContains(lst: List, target: number): boolean {
  switch (lst.tag) { case "Nil": return false; case "Cons": return lst.head === target || listContains(lst.tail, target); }
}
console.assert(listContains({ tag: "Cons", head: 1, tail: { tag: "Cons", head: 2, tail: { tag: "Nil" } } }, 2) === true);
