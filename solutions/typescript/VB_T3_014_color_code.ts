// VB-T3-014: Color to RGB Code -- TypeScript baseline
type Color = { tag: "Red" } | { tag: "Green" } | { tag: "Blue" } | { tag: "Black" };

function colorCode(code: number): number {
  const c: Color =
    code === 0
      ? { tag: "Red" }
      : code === 1
        ? { tag: "Green" }
        : code === 2
          ? { tag: "Blue" }
          : { tag: "Black" };
  switch (c.tag) {
    case "Red":
      return 16711680;
    case "Green":
      return 65280;
    case "Blue":
      return 255;
    case "Black":
      return 0;
  }
}

console.assert(colorCode(0) === 16711680);
console.assert(colorCode(1) === 65280);
console.assert(colorCode(2) === 255);
console.assert(colorCode(3) === 0);
console.assert(colorCode(-1) === 0);
