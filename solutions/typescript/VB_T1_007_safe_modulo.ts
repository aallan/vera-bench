// VB-T1-007: Safe Modulo -- TypeScript baseline
function safeModulo(a: number, b: number): number { return a % b; }
console.assert(safeModulo(10, 3) === 1);
