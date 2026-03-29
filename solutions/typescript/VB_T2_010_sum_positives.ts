// VB-T2-010: Sum Positives -- TypeScript baseline
function sumPositives(arr: number[]): number { return arr.filter(x => x > 0).reduce((a, x) => a + x, 0); }
console.assert(sumPositives([-1,2,-3,4,0]) === 6);
