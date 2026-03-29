// VB-T3-009: List Append -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
function listAppend(xs: List, ys: List): List {
  switch (xs.tag) { case "Nil": return ys; case "Cons": return { tag: "Cons", head: xs.head, tail: listAppend(xs.tail, ys) }; }
}
