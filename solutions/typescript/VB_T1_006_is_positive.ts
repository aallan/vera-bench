// VB-T1-006: Is Positive -- TypeScript baseline
function isPositive(x: number): boolean { return x > 0; }
console.assert(isPositive(5) === true);
console.assert(isPositive(-3) === false);
