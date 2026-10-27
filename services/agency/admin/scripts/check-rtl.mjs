import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const roots = ["app", "components"];
const banned = [
  /margin-left\s*:/g,
  /margin-right\s*:/g,
  /padding-left\s*:/g,
  /padding-right\s*:/g,
  /\bleft\s*:/g,
  /\bright\s*:/g,
];

function walk(path) {
  return readdirSync(path).flatMap((entry) => {
    const full = join(path, entry);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

const violations = [];
for (const root of roots) {
  for (const file of walk(root)) {
    if (!/\.(css|tsx?|mjs)$/.test(file)) continue;
    const source = readFileSync(file, "utf8");
    for (const rule of banned) {
      if (rule.test(source)) violations.push(`${file}: ${rule}`);
      rule.lastIndex = 0;
    }
  }
}

if (violations.length) {
  console.error("RTL logical-property violations detected:\n" + violations.join("\n"));
  process.exit(1);
}

console.log("RTL logical-property check passed.");
