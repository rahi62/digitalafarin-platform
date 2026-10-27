import { config } from "./config.js";

export type RegisteredSite = {
  id: string;
  name: string;
  baseUrl: string;
  username: string;
  lastCheckStatus?: string | null;
  lastCheckedAt?: string | null;
};

export type ResolvedSite = RegisteredSite & {
  appPassword: string;
};

export class SiteRegistryError extends Error {
  constructor(message: string, readonly status = 500) {
    super(message);
    this.name = "SiteRegistryError";
  }
}

const internalHeaders = {
  Accept: "application/json",
  "x-digitalafarin-internal-mcp": "1",
};

export async function listSites(): Promise<RegisteredSite[]> {
  const response = await fetch(config.siteBrokerUrl, {
    headers: internalHeaders,
    signal: AbortSignal.timeout(10_000),
  });
  const data = await response.json().catch(() => null) as { sites?: RegisteredSite[]; error?: string } | null;
  if (!response.ok) throw new SiteRegistryError(data?.error || `Site broker returned HTTP ${response.status}`, response.status);
  return data?.sites ?? [];
}

export async function resolveSite(siteId: string | undefined, operation: string): Promise<ResolvedSite> {
  const sites = await listSites();
  let selected: RegisteredSite | undefined;

  if (siteId) {
    selected = sites.find((site) => site.id === siteId);
    if (!selected) throw new SiteRegistryError("Requested site is not available or is disabled", 404);
  } else if (sites.length === 1) {
    selected = sites[0];
  } else if (sites.length === 0) {
    throw new SiteRegistryError("No enabled WordPress sites are registered", 404);
  } else {
    throw new SiteRegistryError("Multiple WordPress sites are enabled. Call wordpress_list_sites and provide siteId.", 400);
  }

  const url = new URL(config.siteBrokerUrl);
  url.searchParams.set("siteId", selected.id);
  url.searchParams.set("operation", operation);
  const response = await fetch(url, {
    headers: internalHeaders,
    signal: AbortSignal.timeout(10_000),
  });
  const data = await response.json().catch(() => null) as { site?: ResolvedSite; error?: string } | null;
  if (!response.ok || !data?.site) {
    throw new SiteRegistryError(data?.error || `Site broker returned HTTP ${response.status}`, response.status);
  }
  return data.site;
}
