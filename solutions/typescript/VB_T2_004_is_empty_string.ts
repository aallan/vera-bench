// VB-T2-004: Is Empty String -- TypeScript baseline
function isEmptyString(s: string): boolean { return s.length === 0; }
console.assert(isEmptyString("") === true);
console.assert(isEmptyString("hi") === false);
