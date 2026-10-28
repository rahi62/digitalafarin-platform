import https from "node:https";
import { SocksProxyAgent } from "socks-proxy-agent";

/** Only local SOCKS5 is permitted: prevent proxying OAuth credentials to remote hosts. */
export function validProxyPort(port: unknown): number | undefined {
  if (port === "" || port === undefined || port === null) return undefined;
  const number = Number(port);
  if (!Number.isInteger(number) || number < 1 || number > 65535) throw new Error("SOCKS5 port must be between 1 and 65535");
  return number;
}
export async function googleFetch(url: string, init: RequestInit = {}, socksPort?: number): Promise<Response> {
  const target = new URL(url);
  if (target.protocol !== "https:" || !["www.googleapis.com","searchconsole.googleapis.com","oauth2.googleapis.com"].includes(target.hostname)) throw new Error("Unapproved Google endpoint");
  if (!socksPort) return fetch(url, init);
  const agent = new SocksProxyAgent(`socks5h://127.0.0.1:${socksPort}`);
  const headers = new Headers(init.headers);
  const body = init.body == null ? undefined : typeof init.body === "string" ? init.body : init.body instanceof URLSearchParams ? init.body.toString() : undefined;
  if (init.body && body === undefined) throw new Error("Unsupported proxy request body");
  return new Promise<Response>((resolve, reject) => {
    const request = https.request(target, { method: init.method ?? "GET", agent, headers: Object.fromEntries(headers), timeout: 30000 }, (response) => {
      const chunks: Buffer[] = [];
      let size = 0;
      response.on("data", (chunk: Buffer) => { size += chunk.length; if (size > 5_000_000) { request.destroy(new Error("Google response too large")); return; } chunks.push(chunk); });
      response.on("error", reject);
      response.on("end", () => resolve(new Response(Buffer.concat(chunks), { status: response.statusCode ?? 502, headers: { "content-type": String(response.headers["content-type"] ?? "") } })));
    });
    request.on("error", reject);
    request.on("timeout", () => request.destroy(new Error("Google proxy timeout")));
    if (body) request.write(body);
    request.end();
  });
}
