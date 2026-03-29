// VB-T4-004: Power -- TypeScript baseline
function power(base: number, exp: number): number { return exp === 0 ? 1 : base * power(base, exp - 1); }
console.assert(power(2, 10) === 1024);
