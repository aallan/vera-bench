// VB-T3-006: Option Unwrap Or -- TypeScript baseline
type Option = { tag: "None" } | { tag: "Some"; value: number };
function optionUnwrapOr(opt: Option, defaultVal: number): number {
  switch (opt.tag) { case "None": return defaultVal; case "Some": return opt.value; }
}
console.assert(optionUnwrapOr({ tag: "Some", value: 42 }, 0) === 42);
console.assert(optionUnwrapOr({ tag: "None" }, 99) === 99);
