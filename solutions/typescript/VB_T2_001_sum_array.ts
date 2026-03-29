// VB-T2-001: Sum Array -- TypeScript baseline
function sumArray(arr: number[]): number { return arr.reduce((a, x) => a + x, 0); }
console.assert(sumArray([1,2,3,4,5]) === 15);
