// VB-T4-007: Count Digits -- TypeScript baseline
function countDigits(n: number): number { return n < 10 ? 1 : 1 + countDigits(Math.floor(n / 10)); }
console.assert(countDigits(12345) === 5);
