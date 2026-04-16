// VB-T2-012: Ends With Suffix -- TypeScript baseline
function endsWithSuffix(haystack: string, suffix: string): boolean { return haystack.endsWith(suffix); }
console.assert(endsWithSuffix("hello", "llo") === true);
console.assert(endsWithSuffix("hello", "world") === false);
console.assert(endsWithSuffix("", "") === true);
console.assert(endsWithSuffix("abc", "abcd") === false);
