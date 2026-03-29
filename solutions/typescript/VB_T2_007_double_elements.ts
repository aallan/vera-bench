// VB-T2-007: Double Elements -- TypeScript baseline
function doubleElements(arr: number[]): number[] { return arr.map(x => x * 2); }
console.assert(JSON.stringify(doubleElements([1,2,3])) === "[2,4,6]");
