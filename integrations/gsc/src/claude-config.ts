import { readdir, access } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export async function claudeConfigCandidates(): Promise<string[]> {
  const home = os.homedir();
  const roaming = process.env.APPDATA || path.join(home, "AppData", "Roaming");
  const local = process.env.LOCALAPPDATA || path.join(home, "AppData", "Local");
  const results: string[] = [];
  const dataRoot = path.join(local, "Claude-Data");
  try {
    for (const folder of await readdir(dataRoot)) {
      if (!folder.startsWith("claude_")) continue;
      const candidate = path.join(dataRoot, folder, "claude_desktop_config.json");
      try { await access(candidate); results.push(candidate); } catch {}
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  const fallback = path.join(roaming, "Claude", "claude_desktop_config.json");
  try { await access(fallback); results.push(fallback); } catch {}
  return results;
}
