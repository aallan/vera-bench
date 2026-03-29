// VB-T1-001: Absolute Value -- TypeScript baseline
function absoluteValue(x: number): number { return x >= 0 ? x : -x; }
console.assert(absoluteValue(-42) === 42);
