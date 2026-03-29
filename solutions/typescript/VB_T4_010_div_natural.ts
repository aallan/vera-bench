// VB-T4-010: Natural Division -- TypeScript baseline
function divNatural(a: number, b: number): number { return a < b ? 0 : 1 + divNatural(a - b, b); }
console.assert(divNatural(17, 5) === 3);
