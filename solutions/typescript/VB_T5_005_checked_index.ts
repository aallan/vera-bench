// VB-T5-005: Checked Index -- TypeScript baseline
function safeIndex(arr: number[], n: number): number { return n >= arr.length ? -1 : arr[n]; }
console.assert(safeIndex([10,20,30], 1) === 20);
console.assert(safeIndex([10], 5) === -1);
