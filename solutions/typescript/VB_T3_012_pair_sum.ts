// VB-T3-012: Pair Sum -- TypeScript baseline
type Pair = { tag: "MkPair"; first: number; second: number };

function pairSum(a: number, b: number): number {
  const p: Pair = { tag: "MkPair", first: a, second: b };
  return p.first + p.second;
}

console.assert(pairSum(3, 4) === 7);
console.assert(pairSum(0, 0) === 0);
console.assert(pairSum(-5, 5) === 0);
console.assert(pairSum(10, -3) === 7);
console.assert(pairSum(100, 200) === 300);
