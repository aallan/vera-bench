// VeraBench TypeScript Baselines

// === Tier 1 ===

function absoluteValue(x: number): number {
  return x >= 0 ? x : -x;
}

function clamp(value: number, lo: number, hi: number): number {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

function signum(x: number): number {
  if (x > 0) return 1;
  if (x < 0) return -1;
  return 0;
}

// === Tier 2 ===

function sumArray(arr: number[]): number {
  return arr.reduce((acc, x) => acc + x, 0);
}

function filterPositives(arr: number[]): number[] {
  return arr.filter(x => x > 0);
}

function greet(name: string): string {
  return "Hello, " + name + "!";
}

// === Tier 3 ===

type List = { tag: "Nil" } | { tag: "Cons"; head: number; tail: List };

function listLength(lst: List): number {
  switch (lst.tag) {
    case "Nil": return 0;
    case "Cons": return 1 + listLength(lst.tail);
  }
}

type Tree = { tag: "Leaf"; value: number } | { tag: "Branch"; left: Tree; right: Tree };

function treeDepth(t: Tree): number {
  switch (t.tag) {
    case "Leaf": return 1;
    case "Branch": return 1 + Math.max(treeDepth(t.left), treeDepth(t.right));
  }
}

type Expr = { tag: "Lit"; value: number } | { tag: "Add"; left: Expr; right: Expr } | { tag: "Neg"; sub: Expr };

function evalExpr(e: Expr): number {
  switch (e.tag) {
    case "Lit": return e.value;
    case "Add": return evalExpr(e.left) + evalExpr(e.right);
    case "Neg": return -evalExpr(e.sub);
  }
}

// === Tier 4 ===

function fibonacci(n: number): number {
  if (n === 0) return 0;
  if (n === 1) return 1;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

function gcd(a: number, b: number): number {
  if (b === 0) return a;
  return gcd(b, a % b);
}

function isEven(n: number): boolean {
  if (n === 0) return true;
  return isOdd(n - 1);
}

function isOdd(n: number): boolean {
  if (n === 0) return false;
  return isEven(n - 1);
}

// === Tier 5 ===

function countThree(): number {
  let state = 0;
  state = state + 1;
  state = state + 1;
  state = state + 1;
  return state;
}

function safeDiv(a: number, b: number): number {
  if (b === 0) return -1;
  return Math.trunc(a / b);
}

// === Tests ===

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error("FAIL: " + msg);
}

assert(absoluteValue(-42) === 42, "abs(-42)");
assert(clamp(50, 0, 100) === 50, "clamp mid");
assert(clamp(-5, 0, 100) === 0, "clamp lo");
assert(clamp(150, 0, 100) === 100, "clamp hi");
assert(signum(42) === 1, "signum +");
assert(signum(-7) === -1, "signum -");
assert(signum(0) === 0, "signum 0");
assert(sumArray([1,2,3,4,5]) === 15, "sum");
assert(filterPositives([-1,2,-3,4,0]).length === 2, "filter");
assert(greet("Alice") === "Hello, Alice!", "greet");

const nil: List = { tag: "Nil" };
const lst3: List = { tag: "Cons", head: 1, tail: { tag: "Cons", head: 2, tail: { tag: "Cons", head: 3, tail: nil } } };
assert(listLength(nil) === 0, "list nil");
assert(listLength(lst3) === 3, "list 3");

const leaf1: Tree = { tag: "Leaf", value: 1 };
assert(treeDepth(leaf1) === 1, "leaf depth");
assert(treeDepth({ tag: "Branch", left: leaf1, right: { tag: "Branch", left: leaf1, right: leaf1 } }) === 3, "tree depth");

assert(evalExpr({ tag: "Add", left: { tag: "Lit", value: 1 }, right: { tag: "Lit", value: 2 } }) === 3, "eval add");
assert(evalExpr({ tag: "Neg", sub: { tag: "Lit", value: 5 } }) === -5, "eval neg");

assert(fibonacci(10) === 55, "fib 10");
assert(gcd(12, 8) === 4, "gcd");
assert(isEven(4) === true, "even 4");
assert(isEven(7) === false, "even 7");
assert(countThree() === 3, "counter");
assert(safeDiv(10, 2) === 5, "div ok");
assert(safeDiv(7, 0) === -1, "div zero");

console.log("All TypeScript baselines pass.");
