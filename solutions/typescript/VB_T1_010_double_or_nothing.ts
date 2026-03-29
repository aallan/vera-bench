// VB-T1-010: Double or Nothing -- TypeScript baseline
function doubleOrNothing(x: number): number { return x > 0 ? x * 2 : 0; }
console.assert(doubleOrNothing(5) === 10);
console.assert(doubleOrNothing(-3) === 0);
