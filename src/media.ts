import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export type DownloadedImage = {
  bytes: Buffer;
  contentType: "image/jpeg" | "image/png" | "image/webp" | "image/gif";
  filename: string;
  sourceUrl: string;
};

const supportedTypes = new Set<DownloadedImage["contentType"]>([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
]);

function isPrivateIpv4(address: string) {
  const parts = address.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return true;
  const [a, b] = parts;
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    (a === 192 && b === 0) ||
    (a === 198 && (b === 18 || b === 19)) ||
    a >= 224
  );
}

function isPrivateIpv6(address: string) {
  const normalized = address.toLowerCase();
  if (normalized === "::" || normalized === "::1") return true;
  if (normalized.startsWith("fc") || normalized.startsWith("fd") || normalized.startsWith("fe8") || normalized.startsWith("fe9") || normalized.startsWith("fea") || normalized.startsWith("feb") || normalized.startsWith("ff")) return true;
  const mapped = normalized.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  return mapped ? isPrivateIpv4(mapped[1]) : false;
}

function isPrivateAddress(address: string) {
  const family = isIP(address);
  if (family === 4) return isPrivateIpv4(address);
  if (family === 6) return isPrivateIpv6(address);
  return true;
}

async function validateRemoteUrl(url: URL) {
  if (url.protocol !== "https:") throw new Error("Image source URL must use HTTPS");
  if (url.username || url.password) throw new Error("Image source URL must not contain credentials");
  if (url.port && url.port !== "443") throw new Error("Image source URL must use the standard HTTPS port");

  const records = await lookup(url.hostname, { all: true, verbatim: true });
  if (records.length === 0) throw new Error("Image source host could not be resolved");
  if (records.some((record) => isPrivateAddress(record.address))) {
    throw new Error("Image source resolves to a private or reserved network address");
  }
}

function extensionFor(contentType: DownloadedImage["contentType"]) {
  if (contentType === "image/jpeg") return "jpg";
  if (contentType === "image/png") return "png";
  if (contentType === "image/webp") return "webp";
  return "gif";
}

export function sanitizeMediaFilename(value: string, contentType?: DownloadedImage["contentType"]) {
  const raw = value.trim().toLowerCase().replace(/\s+/g, "-");
  const safe = raw.replace(/[^a-z0-9._-]/g, "-").replace(/-+/g, "-").replace(/^-+|-+$/g, "");
  const base = safe || `digitalafarin-image-${Date.now()}`;
  if (/\.(jpe?g|png|webp|gif)$/i.test(base)) return base;
  return contentType ? `${base}.${extensionFor(contentType)}` : base;
}

export function decodeBase64Image(input: { data: string; contentType: string; filename: string }, maxBytes: number): DownloadedImage {
  const contentType = input.contentType.toLowerCase() as DownloadedImage["contentType"];
  if (!supportedTypes.has(contentType)) throw new Error("Unsupported image type. Use JPEG, PNG, WebP, or GIF");
  const normalized = input.data.replace(/^data:image\/[a-z0-9.+-]+;base64,/i, "").replace(/\s+/g, "");
  if (!/^[a-z0-9+/]*={0,2}$/i.test(normalized)) throw new Error("Invalid base64 image data");
  const bytes = Buffer.from(normalized, "base64");
  if (bytes.length === 0) throw new Error("Image data is empty");
  if (bytes.length > maxBytes) throw new Error(`Image exceeds the ${maxBytes}-byte media limit`);
  return { bytes, contentType, filename: sanitizeMediaFilename(input.filename, contentType), sourceUrl: "base64" };
}

export async function downloadImage(source: string, filename: string, maxBytes: number): Promise<DownloadedImage> {
  let current = new URL(source);
  for (let redirect = 0; redirect <= 3; redirect += 1) {
    await validateRemoteUrl(current);
    const response = await fetch(current, {
      redirect: "manual",
      headers: { Accept: "image/jpeg,image/png,image/webp,image/gif", "User-Agent": "DigitalAfarin-WordPress-MCP/0.3" },
      signal: AbortSignal.timeout(25_000),
    });

    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get("location");
      if (!location) throw new Error("Image source returned a redirect without a Location header");
      current = new URL(location, current);
      continue;
    }

    if (!response.ok) throw new Error(`Image download failed with HTTP ${response.status}`);
    const contentType = (response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() || "") as DownloadedImage["contentType"];
    if (!supportedTypes.has(contentType)) throw new Error("Remote URL did not return a supported image type");
    const declaredLength = Number(response.headers.get("content-length") || "0");
    if (declaredLength > maxBytes) throw new Error(`Image exceeds the ${maxBytes}-byte media limit`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length === 0) throw new Error("Downloaded image is empty");
    if (bytes.length > maxBytes) throw new Error(`Image exceeds the ${maxBytes}-byte media limit`);
    return { bytes, contentType, filename: sanitizeMediaFilename(filename, contentType), sourceUrl: current.toString() };
  }
  throw new Error("Image source redirected too many times");
}
