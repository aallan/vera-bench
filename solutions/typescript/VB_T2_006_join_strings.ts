// VB-T2-006: Join Strings -- TypeScript baseline
function joinStrings(arr: string[], sep: string): string { return arr.join(sep); }
console.assert(joinStrings(["a","b","c"], ",") === "a,b,c");
