// VB-T4-005: Sum to N -- TypeScript baseline
function sumToN(n: number): number { return n === 0 ? 0 : n + sumToN(n - 1); }
console.assert(sumToN(10) === 55);
