// VB-T2-014: Combined String Length -- TypeScript baseline
function combinedLength(a: string, b: string): number { return a.length + b.length; }
console.assert(combinedLength("hello", "world") === 10);
console.assert(combinedLength("", "") === 0);
console.assert(combinedLength("a", "bc") === 3);
console.assert(combinedLength("test", "") === 4);
