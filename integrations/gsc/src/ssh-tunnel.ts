import { spawn, type ChildProcess } from "node:child_process";
import net from "node:net";

export type SshTunnelConfig = {
  host: string; user: string; keyPath: string; port: number; useWsl: boolean;
};
export function validateSshConfig(value: SshTunnelConfig): SshTunnelConfig {
  if (!/^(?:[a-zA-Z0-9][a-zA-Z0-9.-]{0,251}|\\[[0-9a-fA-F:]+\\])$/.test(value.host)) throw new Error("Invalid SSH hostname");
  if (!/^[a-zA-Z_][a-zA-Z0-9_-]{0,31}$/.test(value.user)) throw new Error("Invalid SSH username");
  if (!value.keyPath || value.keyPath.length > 512 || /[\r\n\0]/.test(value.keyPath) || value.keyPath.startsWith("-")) throw new Error("Invalid SSH key path");
  if (!Number.isInteger(value.port) || value.port < 1024 || value.port > 65535) throw new Error("Invalid local SSH SOCKS port");
  return value;
}
function probe(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host: "127.0.0.1", port });
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("error", () => { socket.destroy(); resolve(false); });
    socket.setTimeout(1000, () => { socket.destroy(); resolve(false); });
  });
}
let owned: ChildProcess | undefined;
let starting: Promise<void> | undefined;
export async function ensureSshTunnel(config: SshTunnelConfig): Promise<void> {
  validateSshConfig(config);
  if (owned?.exitCode === null && !owned.killed && await probe(config.port)) return;
  if (starting) return starting;
  starting = (async () => {
    // Never trust or reuse a listener from an unrelated process.
    if (await probe(config.port)) throw new Error(`SSH port ${config.port} already occupied. Close the old tunnel or select another port.`);
    const args = [
      "-i", config.keyPath, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
      "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
      "-o", "StrictHostKeyChecking=yes", "-o", "ExitOnForwardFailure=yes",
      "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=2",
      "-N", "-D", `127.0.0.1:${config.port}`, `${config.user}@${config.host}`
    ];
    const child = spawn(config.useWsl ? "wsl.exe" : "ssh.exe", config.useWsl ? ["--", "ssh", ...args] : args, {
      windowsHide: true, stdio: ["ignore", "ignore", "pipe"]
    });
    owned = child;
    let stderr = "";
    child.stderr?.on("data", (chunk: Buffer) => { stderr = (stderr + chunk.toString()).slice(-2000); });
    const failed = new Promise<never>((_, reject) => {
      child.once("error", () => reject(new Error("SSH executable could not start")));
      child.once("exit", (code) => reject(new Error(`SSH tunnel exited (${code}): ${stderr.slice(-400)}`)));
    });
    try {
      const ready = (async () => {
        for (let attempt = 0; attempt < 40; attempt++) {
          if (await probe(config.port)) return;
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
        throw new Error("SSH tunnel did not become reachable on Windows localhost");
      })();
      await Promise.race([ready, failed]);
    } catch (error) {
      child.kill();
      owned = undefined;
      throw error;
    }
  })();
  try { await starting; } finally { starting = undefined; }
}
export function stopOwnedSshTunnel() {
  const child = owned;
  owned = undefined;
  if (child && child.exitCode === null) child.kill();
}
