// VB-T1-003: Signum -- TypeScript baseline
function signum(x: number): number {
  if (x > 0) return 1;
  if (x < 0) return -1;
  return 0;
}
console.assert(signum(42) === 1);
console.assert(signum(-7) === -1);
console.assert(signum(0) === 0);
