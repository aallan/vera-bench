// VB-T2-011: Starts With Prefix -- TypeScript baseline
function startsWithPrefix(haystack: string, prefix: string): boolean { return haystack.startsWith(prefix); }
console.assert(startsWithPrefix("hello", "hel") === true);
console.assert(startsWithPrefix("hello", "world") === false);
console.assert(startsWithPrefix("", "") === true);
console.assert(startsWithPrefix("abc", "abcd") === false);
