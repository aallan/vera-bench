// VB-T4-003: Even/Odd -- TypeScript baseline
function isEven(n: number): boolean { return n === 0 ? true : isOdd(n - 1); }
function isOdd(n: number): boolean { return n === 0 ? false : isEven(n - 1); }
console.assert(isEven(4) === true);
console.assert(isEven(7) === false);
