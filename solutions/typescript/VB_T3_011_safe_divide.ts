// VB-T3-011: Safe Divide -- TypeScript baseline
type Result = { tag: "Failure" } | { tag: "Success"; value: number };

function safeDivide(a: number, b: number): number {
  const r: Result = b === 0 ? { tag: "Failure" } : { tag: "Success", value: Math.trunc(a / b) };
  switch (r.tag) {
    case "Failure":
      return -1;
    case "Success":
      return r.value;
  }
}

console.assert(safeDivide(10, 2) === 5);
console.assert(safeDivide(7, 3) === 2);
console.assert(safeDivide(10, 0) === -1);
console.assert(safeDivide(0, 5) === 0);
console.assert(safeDivide(-6, 3) === -2);
