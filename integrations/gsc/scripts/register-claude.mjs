import { readFile, writeFile, copyFile, rename, mkdir, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import os from "node:os";

if (process.platform !== "win32") throw new Error("This installer is for Claude Desktop on Windows.");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const entry = join(root, "dist", "index.js");
await access(entry).catch(() => { throw new Error("Build first: npm run build"); });
const appdata = process.env.APPDATA || join(os.homedir(), "AppData", "Roaming");
const dir = join(appdata, "Claude");
const file = join(dir, "claude_desktop_config.json");
await mkdir(dir, { recursive: true });
let existing = {};
let original;
try { original = await readFile(file, "utf8"); } catch (error) {
  if (error.code !== "ENOENT") throw error;
}
if (original !== undefined) {
  try { existing = JSON.parse(original); } catch { throw new Error("Claude configuration is invalid JSON. No changes made."); }
  if (!existing || typeof existing !== "object" || Array.isArray(existing)) throw new Error("Claude config root must be an object.");
}
if (existing.mcpServers !== undefined && (!existing.mcpServers || typeof existing.mcpServers !== "object" || Array.isArray(existing.mcpServers)))
  throw new Error("Claude mcpServers must be an object. No changes made.");
const servers = existing.mcpServers || {};
if (servers["digitalafarin-gsc"]) throw new Error("digitalafarin-gsc already exists. Edit or back up explicitly; no changes made.");
const command = process.execPath;
servers["digitalafarin-gsc"] = { command, args: [entry] };
existing.mcpServers = servers;
const temp = file + ".tmp-" + process.pid;
if (original !== undefined) {
  const backup = file + ".bak-" + new Date().toISOString().replace(/[:.]/g, "-");
  await copyFile(file, backup);
  console.log("Existing Claude config backed up.");
}
await writeFile(temp, JSON.stringify(existing, null, 2) + "\n", { encoding: "utf8", flag: "wx" });
await rename(temp, file);
console.log("Registered digitalafarin-gsc. Existing MCP entries retained. Restart Claude Desktop.");
