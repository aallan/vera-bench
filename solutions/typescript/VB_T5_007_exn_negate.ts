// VB-T5-007: Exception on Negative -- TypeScript baseline
function safeNonNegative(x: number): number { return x < 0 ? 0 : x; }
console.assert(safeNonNegative(5) === 5);
console.assert(safeNonNegative(-3) === 0);
