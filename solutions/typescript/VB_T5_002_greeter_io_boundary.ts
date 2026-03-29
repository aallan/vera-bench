// VB-T5-002: Greeter IO Boundary -- TypeScript baseline
function buildGreeting(name: string): string { return "Hello, " + name + "!\n"; }
function greetIO(name: string): void { process.stdout.write(buildGreeting(name)); }
console.assert(buildGreeting("Alice") === "Hello, Alice!\n");
