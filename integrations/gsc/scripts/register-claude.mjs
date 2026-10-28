import { readFile, writeFile, copyFile, rename, mkdir, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import os from "node:os";

if (process.platform !== "win32") throw new Error("This installer is for Claude Desktop on Windows.");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const entry = join(root, "dist", "index.js");
await access(entry).catch(() => { throw new Error("Build first: npm run build"); });
const appdata = process.env.APPDATA || join(os.homedir(), "AppData", "Roaming");
const localappdata = process.env.LOCALAPPDATA || join(os.homedir(), "AppData", "Local");
const roamingFile = join(appdata, "Claude", "claude_desktop_config.json");
const { readdir } = await import("node:fs/promises");
const localRoot = join(localappdata, "Claude-Data");
const localFiles = [];
try {
  for (const name of await readdir(localRoot)) {
    if (!name.startsWith("claude_")) continue;
    const candidate = join(localRoot, name, "claude_desktop_config.json");
    try { await access(candidate); localFiles.push(candidate); } catch {}
  }
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
let file;
if (localFiles.length === 1) file = localFiles[0];
else if (localFiles.length > 1) throw new Error("Multiple Claude-Data profiles found. Set CLAUDE_CONFIG_PATH to the intended JSON file.");
else file = roamingFile;
if (process.env.CLAUDE_CONFIG_PATH) file = resolve(process.env.CLAUDE_CONFIG_PATH);
const dir = dirname(file);
await mkdir(dir, { recursive: true });
console.log("Claude configuration:", file);
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
if (servers["digitalafarin-gsc"] && !process.argv.includes("--update")) throw new Error("digitalafarin-gsc already exists. Run with --update to back up and replace only this entry.");
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
