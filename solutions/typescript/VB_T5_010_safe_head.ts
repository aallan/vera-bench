// VB-T5-010: Safe Head -- TypeScript baseline
function safeHead(arr: number[]): number { return arr.length === 0 ? -1 : arr[0]; }
console.assert(safeHead([10,20]) === 10);
console.assert(safeHead([]) === -1);
