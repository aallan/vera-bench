// VB-T4-006: List Reverse -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
function listReverse(lst: List): List {
  function go(xs: List, acc: List): List {
    switch (xs.tag) { case "Nil": return acc; case "Cons": return go(xs.tail, { tag: "Cons", head: xs.head, tail: acc }); }
  }
  return go(lst, { tag: "Nil" });
}
