// VB-T2-005: Contains Substring -- TypeScript baseline
function containsSubstring(haystack: string, needle: string): boolean { return haystack.includes(needle); }
console.assert(containsSubstring("hello world", "world") === true);
