// VB-T5-003: Safe Division -- TypeScript baseline
function safeDiv(a: number, b: number): number {
  if (b === 0) return -1;
  return Math.trunc(a / b);
}
console.assert(safeDiv(10, 2) === 5);
console.assert(safeDiv(7, 0) === -1);
