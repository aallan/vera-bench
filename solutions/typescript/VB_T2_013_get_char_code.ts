// VB-T2-013: Get Char Code -- TypeScript baseline
function getCharCode(s: string, index: number): number { return s.charCodeAt(index); }
console.assert(getCharCode("A", 0) === 65);
console.assert(getCharCode("hello", 0) === 104);
console.assert(getCharCode("hello", 4) === 111);
console.assert(getCharCode("Z", 0) === 90);
