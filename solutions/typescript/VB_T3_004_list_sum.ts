// VB-T3-004: List Sum -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
function listSum(lst: List): number {
  switch (lst.tag) { case "Nil": return 0; case "Cons": return lst.head + listSum(lst.tail); }
}
console.assert(listSum({ tag: "Cons", head: 1, tail: { tag: "Cons", head: 2, tail: { tag: "Nil" } } }) === 3);
