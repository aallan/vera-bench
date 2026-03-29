// VB-T4-001: Fibonacci -- TypeScript baseline
function fibonacci(n: number): number { if (n <= 1) return n; return fibonacci(n-1) + fibonacci(n-2); }
console.assert(fibonacci(10) === 55);
