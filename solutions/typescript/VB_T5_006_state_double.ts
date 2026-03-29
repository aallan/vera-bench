// VB-T5-006: State Double -- TypeScript baseline
function stateDouble(x: number): number { let s = x; s = s * 2; return s; }
console.assert(stateDouble(21) === 42);
