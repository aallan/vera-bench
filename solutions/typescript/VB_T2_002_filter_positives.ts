// VB-T2-002: Filter Positives -- TypeScript baseline
function filterPositives(arr: number[]): number[] { return arr.filter(x => x > 0); }
console.assert(filterPositives([-1,2,-3,4,0]).length === 2);
