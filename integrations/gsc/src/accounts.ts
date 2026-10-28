import { randomBytes } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const directory = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "DigitalAfarin", "GSC");
const filename = path.join(directory, "accounts.json");

export type Account = { id: string; label: string; encryptedRefreshToken: string };
export type Settings = { clientId: string; encryptedClientSecret?: string; accounts: Account[] };
export async function load(): Promise<Settings> {
  try {
    const data = JSON.parse(await readFile(filename, "utf8")) as Settings;
    return { clientId: data.clientId || "", encryptedClientSecret: data.encryptedClientSecret, accounts: Array.isArray(data.accounts) ? data.accounts : [] };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { clientId: "", accounts: [] };
    throw error;
  }
}
export async function save(value: Settings): Promise<void> {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const temporary = path.join(directory, `.accounts-${randomBytes(8).toString("hex")}.tmp`);
  await writeFile(temporary, JSON.stringify(value), { encoding: "utf8", mode: 0o600, flag: "wx" });
  const { rename } = await import("node:fs/promises");
  await rename(temporary, filename);
}

/** Windows DPAPI: encrypted tokens bound to the current Windows logon. */
function runPowerShell(script: string, input: string): Promise<string> {
  if (process.platform !== "win32") throw new Error("Secure account storage is currently supported on Windows only");
  return new Promise((resolve, reject) => {
    const child = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
      stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
    });
    let output = "", error = "";
    child.stdout.on("data", (chunk: Buffer) => { output += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk: Buffer) => { error += chunk.toString("utf8"); });
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolve(output.trim()) : reject(new Error("Windows credential protection failed")));
    child.stdin.end(input);
  });
}
export async function protect(plaintext: string): Promise<string> {
  const script = `Add-Type -AssemblyName System.Security; $raw=[Console]::In.ReadToEnd(); $bytes=[System.Text.Encoding]::UTF8.GetBytes($raw); $encrypted=[System.Security.Cryptography.ProtectedData]::Protect($bytes,$null,[System.Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Out.Write([Convert]::ToBase64String($encrypted))`;
  return runPowerShell(script, plaintext);
}
export async function unprotect(ciphertext: string): Promise<string> {
  const script = `Add-Type -AssemblyName System.Security; $raw=[Console]::In.ReadToEnd(); $bytes=[Convert]::FromBase64String($raw); $decrypted=[System.Security.Cryptography.ProtectedData]::Unprotect($bytes,$null,[System.Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Out.Write([System.Text.Encoding]::UTF8.GetString($decrypted))`;
  return runPowerShell(script, ciphertext);
}
export async function googleToken(clientId: string, refreshToken: string, encryptedClientSecret?: string): Promise<string> {
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST", redirect: "error", signal: AbortSignal.timeout(15000),
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: clientId, ...(encryptedClientSecret ? { client_secret: await unprotect(encryptedClientSecret) } : {}), refresh_token: refreshToken, grant_type: "refresh_token" }),
  });
  if (!response.ok) throw new Error(`Google authorization failed (HTTP ${response.status}). Reconnect the account.`);
  const data = await response.json() as { access_token?: string };
  if (!data.access_token) throw new Error("Google did not return an access token");
  return data.access_token;
}
