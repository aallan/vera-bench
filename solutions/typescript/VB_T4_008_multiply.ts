// VB-T4-008: Multiply -- TypeScript baseline
function multiply(a: number, b: number): number { return b === 0 ? 0 : a + multiply(a, b - 1); }
console.assert(multiply(7, 6) === 42);
