// VB-T5-009: State Max -- TypeScript baseline
function stateMax(n: number): number { let s = 0; for (let i = 1; i <= n; i++) s = Math.max(s, i); return s; }
console.assert(stateMax(5) === 5);
