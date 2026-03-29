// VB-T4-002: GCD -- TypeScript baseline
function gcd(a: number, b: number): number { return b === 0 ? a : gcd(b, a % b); }
console.assert(gcd(12, 8) === 4);
