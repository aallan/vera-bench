// VB-T3-010: List Last -- TypeScript baseline
type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };
type Option = { tag: "None" } | { tag: "Some"; value: number };
function listLast(lst: List): Option {
  switch (lst.tag) {
    case "Nil": return { tag: "None" };
    case "Cons": return lst.tail.tag === "Nil" ? { tag: "Some", value: lst.head } : listLast(lst.tail);
  }
}
