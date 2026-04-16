// VB-T3-013: Classify Sign -- TypeScript baseline
type Sign = { tag: "Negative" } | { tag: "Zero" } | { tag: "Positive" };

function classifySign(n: number): number {
  const s: Sign = n < 0 ? { tag: "Negative" } : n === 0 ? { tag: "Zero" } : { tag: "Positive" };
  switch (s.tag) {
    case "Negative":
      return -1;
    case "Zero":
      return 0;
    case "Positive":
      return 1;
  }
}

console.assert(classifySign(42) === 1);
console.assert(classifySign(-7) === -1);
console.assert(classifySign(0) === 0);
console.assert(classifySign(1) === 1);
console.assert(classifySign(-100) === -1);
