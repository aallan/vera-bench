// VB-T5-004: Accumulator -- TypeScript baseline
function sumWithState(n: number): number { let s = 0; for (let i = 1; i <= n; i++) s += i; return s; }
console.assert(sumWithState(5) === 15);
