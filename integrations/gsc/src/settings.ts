import http from "node:http";
import { randomBytes, createHash } from "node:crypto";
import { load, save, protect, unprotect, googleToken } from "./accounts.js";
import { googleRead, READONLY_SCOPE } from "./google-api.js";

const host = "127.0.0.1";
const port = 47861;
const redirectUri = `http://${host}:${port}/oauth/callback`;
let pending: { state: string; verifier: string; expiresAt: number } | undefined;
const formNonce = randomBytes(32).toString("hex");
function csrfField() { return `<input type="hidden" name="csrf" value="${formNonce}">`; }
function html(body: string) {
  return `<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DigitalAfarin GSC</title><style>
  *{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#14243c;font:15px Tahoma,"Segoe UI",sans-serif;line-height:1.9}.wrap{max-width:780px;margin:7vh auto;padding:0 18px}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}h1{font-size:24px;margin:0}small,.muted{color:#61738a}.card{background:white;border:1px solid #e1e8f2;border-radius:20px;padding:24px;margin:16px 0;box-shadow:0 5px 28px #1f36510a}h2{font-size:17px;margin:0 0 14px}input{padding:12px;width:100%;border:1px solid #cbd7e6;border-radius:11px;margin:9px 0 16px;direction:ltr;text-align:left;background:white;color:#14243c}button,.button{display:inline-block;border:0;background:#245fdf;color:white;padding:11px 20px;border-radius:11px;font:inherit;cursor:pointer;text-decoration:none}.danger{background:#fff2f3;color:#ad2638}.item{display:flex;gap:14px;align-items:center;justify-content:space-between;border-top:1px solid #e9eef5;padding:14px 0}.note{background:#eff5ff;padding:12px;border-radius:12px;color:#315487}</style><div class="wrap"><div class="head"><h1>DigitalAfarin GSC Connector</h1><small>اتصال فقط‌خواندنی</small></div>${body}</div></html>`;
}
function escape(value: string) { return value.replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" })[c]!); }
function respond(res: http.ServerResponse, status: number, content: string, type = "text/html; charset=utf-8") {
  res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'", "Referrer-Policy": "no-referrer" });
  res.end(content);
}
function back(res: http.ServerResponse, status = "saved") { res.writeHead(303, { Location: `/?status=${encodeURIComponent(status)}`, "Cache-Control": "no-store" }); res.end(); }
async function formBody(req: http.IncomingMessage) {
  let body = "";
  for await (const chunk of req) { body += String(chunk); if (body.length > 8192) throw new Error("Request too large"); }
  return new URLSearchParams(body);
}
function pkceChallenge(verifier: string) { return createHash("sha256").update(verifier).digest("base64url"); }
export async function runSettings() {
  const server = http.createServer(async (req, res) => {
    try {
      // Accept the two standard loopback hostnames, never LAN or arbitrary hosts.
      const authority = req.headers.host;
      if (authority !== `127.0.0.1:${port}` && authority !== `localhost:${port}`)
        return respond(res, 403, "Forbidden: invalid local host");
      const url = new URL(req.url ?? "/", `http://${authority}/`);
      if (req.method === "POST") {
        const origin = req.headers.origin;
        // Origin is optional for browser form posts. When supplied it must match
        // the exact loopback authority; reject explicit cross-site Fetch Metadata.
        // The separate per-process CSRF form token is mandatory below.
        // The settings UI is bound to IPv4 loopback and every form carries a
        // random per-process CSRF token. Browsers may report localhost and
        // 127.0.0.1 as different origins; do not trust either header alone.
        const localOrigins = new Set([`http://127.0.0.1:${port}`, `http://localhost:${port}`]);
        // Some privacy/browser contexts send Origin: null even for a loopback
        // form. It is acceptable ONLY with a valid, unguessable CSRF token,
        // checked below. All other foreign origins remain rejected.
        if (origin && origin !== "null" && !localOrigins.has(origin))
          return respond(res, 403, "Forbidden: invalid request origin");
        const body = await formBody(req);
        if (body.get("csrf") !== formNonce) return respond(res, 403, "Forbidden");
        if (url.pathname === "/client") {
          const clientId = (body.get("clientId") ?? "").trim();
          const clientSecret = (body.get("clientSecret") ?? "").trim();
          if (!/^\d+-[a-z0-9_-]+\.apps\.googleusercontent\.com$/.test(clientId)) throw new Error("Google OAuth Client ID is invalid");
          const settings = await load();
          if (settings.accounts.length && settings.clientId !== clientId) throw new Error("Disconnect accounts before changing OAuth client");
          if (settings.clientId !== clientId) settings.encryptedClientSecret = undefined;
          settings.clientId = clientId;
          if (clientSecret) settings.encryptedClientSecret = await protect(clientSecret);
          await save(settings); return back(res, "saved");
        }
        if (url.pathname === "/remove") {
          const settings = await load();
          settings.accounts = settings.accounts.filter((a) => a.id !== body.get("id"));
          await save(settings); return back(res);
        }
      }
      if (url.pathname === "/oauth/start" && req.method === "POST") {
        const settings = await load();
        if (!settings.clientId) throw new Error("Configure Google OAuth Client ID first");
        const state = randomBytes(32).toString("base64url");
        const verifier = randomBytes(48).toString("base64url");
        pending = { state, verifier, expiresAt: Date.now() + 5 * 60_000 };
        const params = new URLSearchParams({
          client_id: settings.clientId, redirect_uri: redirectUri, response_type: "code",
          scope: READONLY_SCOPE, access_type: "offline", prompt: "consent",
          state, code_challenge: pkceChallenge(verifier), code_challenge_method: "S256",
        });
        res.writeHead(302, { Location: `https://accounts.google.com/o/oauth2/v2/auth?${params}`, "Cache-Control": "no-store" });res.end();return;
      }
      if (url.pathname === "/oauth/callback" && req.method === "GET") {
        const current = pending; pending = undefined;
        if (!current || Date.now() > current.expiresAt || url.searchParams.get("state") !== current.state) throw new Error("OAuth state invalid or expired");
        const code = url.searchParams.get("code");
        if (!code || url.searchParams.has("error")) throw new Error("Google authorization was cancelled or failed");
        const settings = await load();
        const response = await fetch("https://oauth2.googleapis.com/token", {
          method: "POST", redirect: "error", signal: AbortSignal.timeout(15000),
          headers: { "content-type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ client_id: settings.clientId, ...(settings.encryptedClientSecret ? { client_secret: await unprotect(settings.encryptedClientSecret) } : {}), code, code_verifier: current.verifier, redirect_uri: redirectUri, grant_type: "authorization_code" }),
        });
        if (!response.ok) throw new Error(`Google token exchange failed: HTTP ${response.status}`);
        const token = await response.json() as { access_token?: string; refresh_token?: string };
        if (!token.access_token || !token.refresh_token) throw new Error("Google did not provide offline access; retry connection");
        const properties = await googleRead<{siteEntry?: unknown[]}>(token.access_token, "https://www.googleapis.com/webmasters/v3/sites");
        const id = randomBytes(12).toString("hex");
        settings.accounts.push({ id, label: `Google account ${settings.accounts.length + 1} (${properties.siteEntry?.length ?? 0} properties)`, encryptedRefreshToken: await protect(token.refresh_token) });
        await save(settings);
        return back(res, "connected");
      }
      if (url.pathname === "/properties" && req.method === "GET") {
        const settings = await load();
        const account = settings.accounts.find((item) => item.id === url.searchParams.get("id"));
        if (!account) return respond(res, 404, "Account not found");
        const token = await googleToken(settings.clientId, await unprotect(account.encryptedRefreshToken), settings.encryptedClientSecret);
        const payload = await googleRead<{ siteEntry?: Array<{ siteUrl: string; permissionLevel: string }> }>(token, "https://www.googleapis.com/webmasters/v3/sites");
        const items = (payload.siteEntry ?? []).map((entry) => `<div class="item"><div><strong dir="ltr">${escape(entry.siteUrl)}</strong><small> ${escape(entry.permissionLevel)}</small></div></div>`).join("");
        return respond(res, 200, html(`<div class="card"><h2>Propertyهای ${escape(account.label)}</h2>${items || '<p class="muted">Property در دسترس نیست.</p>'}<a href="/">بازگشت به تنظیمات</a></div>`));
      }
      if (url.pathname === "/" && req.method === "GET") {
        const settings = await load();
        const notice = url.searchParams.get("status") === "saved" ? '<div class="note" role="status">تنظیمات با موفقیت ذخیره شد.</div>' : url.searchParams.get("status") === "connected" ? '<div class="note" role="status">حساب Google با موفقیت متصل شد.</div>' : "";
        const accounts = settings.accounts.map((a) => `<div class="item"><div><strong>${escape(a.label)}</strong><div class="muted">حساب متصل به‌صورت امن روی ویندوز ذخیره شده است</div><a href="/properties?id=${encodeURIComponent(a.id)}">مشاهده Propertyها و تست اتصال</a></div><form method="post" action="/remove">${csrfField()}<input type="hidden" name="id" value="${escape(a.id)}"><button class="danger">قطع اتصال</button></form></div>`).join("");
        return respond(res, 200, html(`${notice}<div class="card"><h2>تنظیمات Google OAuth</h2><div class="muted">یک OAuth Client از نوع Desktop در Google Cloud بسازید. Client ID لازم است؛ اگر Google برای OAuth Client شما Client Secret ارائه کرده، آن را هم وارد کنید.</div><form method="post" action="/client">${csrfField()}<label for="clientId">Client ID</label><input id="clientId" name="clientId" required value="${escape(settings.clientId)}"><label for="clientSecret">Client Secret (اختیاری؛ مقدار ذخیره‌شده نمایش داده نمی‌شود)</label><input id="clientSecret" type="password" name="clientSecret" autocomplete="off" placeholder="${settings.encryptedClientSecret ? "قبلاً ثبت شده" : "در صورت ارائه توسط Google"}"><button>ذخیره تنظیمات</button></form></div><div class="card"><h2>حساب‌های متصل</h2>${accounts || '<p class="muted">هنوز حسابی متصل نیست.</p>'}<form method="post" action="/oauth/start">${csrfField()}<button type="submit">+ افزودن حساب Google</button></form></div><div class="note">دسترسی فقط‌خواندنی است؛ Claude تحلیل‌ها را انجام می‌دهد. این پنل فقط روی همین کامپیوتر باز است.</div>`));
      }
      return respond(res, 404, "Not found");
    } catch (error) {
      return respond(res, 400, html(`<div class="card"><h2>اتصال انجام نشد</h2><p>${escape(error instanceof Error ? error.message : "Unknown error")}</p><a href="/">بازگشت</a></div>`));
    }
  });
  server.listen(port, host, () => console.error(`DigitalAfarin GSC settings: http://${host}:${port}/`));
}
