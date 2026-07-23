// VB-T1-002: Clamp -- TypeScript baseline
function clampToRange(value: number, lo: number, hi: number): number {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}
console.assert(clampToRange(50, 0, 100) === 50);
console.assert(clampToRange(-5, 0, 100) === 0);
