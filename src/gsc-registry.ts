import { config } from "./config.js";

export type RegisteredGscSite = {
  id: string;
  name: string;
  baseUrl: string;
  propertyUrl: string;
};

export type ResolvedGscSite = {
  site: RegisteredGscSite;
  accessToken: string;
};

export class GscRegistryError extends Error {
  constructor(message: string, readonly status = 500, readonly code = "gsc_registry_error") {
    super(message);
    this.name = "GscRegistryError";
  }
}

export function classifyGscRegistryFailure(data: { error?: string; status: number; code?: string }) {
  const code = data.code === "gsc_reauthorization_required" || data.code === "gsc_refresh_failed"
    ? data.code
    : "gsc_registry_error";
  return new GscRegistryError(data.error || `GSC broker returned HTTP ${data.status}`, data.status, code);
}

const internalHeaders = {
  Accept: "application/json",
  "x-digitalafarin-internal-mcp": "1",
};

export async function listGscSites(): Promise<RegisteredGscSite[]> {
  const response = await fetch(config.gscBrokerUrl, {
    headers: internalHeaders,
    signal: AbortSignal.timeout(15_000),
  });
  const data = await response.json().catch(() => null) as { sites?: RegisteredGscSite[]; error?: string; code?: string } | null;
  if (!response.ok) throw new GscRegistryError(data?.error || `GSC broker returned HTTP ${response.status}`, response.status);
  return data?.sites ?? [];
}

export async function resolveGscSite(siteId: string | undefined, operation: string): Promise<ResolvedGscSite> {
  const sites = await listGscSites();
  let selected: RegisteredGscSite | undefined;
  if (siteId) {
    selected = sites.find((site) => site.id === siteId);
    if (!selected) throw new GscRegistryError("Requested site has no enabled Search Console property mapping", 404);
  } else if (sites.length === 1) {
    selected = sites[0];
  } else if (sites.length === 0) {
    throw new GscRegistryError("No enabled WordPress site is mapped to a Search Console property", 404);
  } else {
    throw new GscRegistryError("Multiple GSC-mapped sites are available. Call gsc_list_sites and provide siteId.", 400);
  }

  const url = new URL(config.gscBrokerUrl);
  url.searchParams.set("siteId", selected.id);
  url.searchParams.set("operation", operation);
  const response = await fetch(url, {
    headers: internalHeaders,
    signal: AbortSignal.timeout(20_000),
  });
  const data = await response.json().catch(() => null) as { site?: RegisteredGscSite; accessToken?: string; error?: string; code?: string } | null;
  if (!response.ok || !data?.site || !data.accessToken) {
    throw classifyGscRegistryFailure({ error: data?.error, code: data?.code, status: response.status });
  }
  return { site: data.site, accessToken: data.accessToken };
}
