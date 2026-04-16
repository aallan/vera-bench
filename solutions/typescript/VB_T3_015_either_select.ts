// VB-T3-015: Either Select -- TypeScript baseline
type Either = { tag: "Left"; value: number } | { tag: "Right"; value: number };

function eitherSelect(a: number, b: number, selector: number): number {
  const e: Either = selector > 0 ? { tag: "Left", value: a } : { tag: "Right", value: b };
  switch (e.tag) {
    case "Left":
      return e.value;
    case "Right":
      return e.value;
  }
}

console.assert(eitherSelect(10, 20, 1) === 10);
console.assert(eitherSelect(10, 20, 0) === 20);
console.assert(eitherSelect(10, 20, -5) === 20);
console.assert(eitherSelect(42, 99, 100) === 42);
console.assert(eitherSelect(0, 0, 1) === 0);
