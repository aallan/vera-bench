// VB-T2-015: Is Longer Than -- TypeScript baseline
function isLongerThan(s: string, threshold: number): boolean { return s.length > threshold; }
console.assert(isLongerThan("hello", 3) === true);
console.assert(isLongerThan("hi", 5) === false);
console.assert(isLongerThan("", 0) === false);
console.assert(isLongerThan("test", 4) === false);
console.assert(isLongerThan("test", 3) === true);
