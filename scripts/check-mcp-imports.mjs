#!/usr/bin/env node
/** Read-only monorepo import preflight, no network/deploy/mutations. */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const modules = ["agency", "wordpress"];
let failed = false;
for (const moduleName of modules) {
  const dir = path.join(root, "services", moduleName);
  const packagePath = path.join(dir, "package.json");
  const lockPath = path.join(dir, "package-lock.json");
  if (!existsSync(packagePath) || !existsSync(lockPath)) {
    console.error(`FAIL ${moduleName}: missing package.json or package-lock.json`);
    failed = true;
    continue;
  }
  const pkg = JSON.parse(readFileSync(packagePath, "utf8"));
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  const rootLock = lock.packages?.[""] ?? {};
  const diff = [];
  if (pkg.version !== rootLock.version) diff.push(`version ${pkg.version} != ${rootLock.version}`);
  for (const kind of ["dependencies", "devDependencies", "optionalDependencies"]) {
    const declared = pkg[kind] ?? {}, locked = rootLock[kind] ?? {};
    const names = new Set([...Object.keys(declared), ...Object.keys(locked)]);
    for (const name of names) {
      if (declared[name] !== locked[name]) diff.push(`${kind}:${name} package=${declared[name] ?? "<absent>"} lock=${locked[name] ?? "<absent>"}`);
    }
  }
  if (diff.length) {
    failed = true;
    console.error(`FAIL ${moduleName}: package/lock mismatch\n  ${diff.join("\n  ")}`);
  } else {
    console.log(`PASS ${moduleName}: package/lock root manifest consistent`);
  }
}
if (failed) process.exitCode = 1;
