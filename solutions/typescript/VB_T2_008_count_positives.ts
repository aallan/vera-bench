// VB-T2-008: Count Positives -- TypeScript baseline
function countPositives(arr: number[]): number { return arr.filter(x => x > 0).length; }
console.assert(countPositives([-1,2,-3,4,0]) === 2);
