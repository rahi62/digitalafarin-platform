export type GscDimension = "query" | "page" | "country" | "device" | "searchAppearance" | "date" | "hour";
export type GscSearchType = "web" | "image" | "video" | "news" | "discover" | "googleNews";
export type GscFilterOperator = "contains" | "equals" | "notContains" | "notEquals" | "includingRegex" | "excludingRegex";

export type GscFilter = {
  dimension: Exclude<GscDimension, "date" | "hour">;
  operator: GscFilterOperator;
  expression: string;
};

export type GscQueryInput = {
  startDate: string;
  endDate: string;
  dimensions?: GscDimension[];
  type?: GscSearchType;
  filters?: GscFilter[];
  rowLimit?: number;
  startRow?: number;
  dataState?: "final" | "all" | "hourly_all";
  aggregationType?: "auto" | "byPage" | "byProperty";
};

export type GscQueryResponse = {
  rows?: Array<{
    keys?: string[];
    clicks?: number;
    impressions?: number;
    ctr?: number;
    position?: number;
  }>;
  responseAggregationType?: string;
  metadata?: Record<string, unknown>;
};

export class GscApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "GscApiError";
  }
}

async function gscJson<T>(url: string, accessToken: string, init: RequestInit = {}) {
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      "User-Agent": "DigitalAfarin-WordPress-MCP/0.5",
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(30_000),
  });
  const data = await response.json().catch(() => null) as (T & { error?: { message?: string } }) | null;
  if (!response.ok || !data) {
    throw new GscApiError(data?.error?.message || `Search Console API returned HTTP ${response.status}`, response.status);
  }
  return data;
}

export async function querySearchAnalytics(accessToken: string, propertyUrl: string, input: GscQueryInput) {
  const url = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(propertyUrl)}/searchAnalytics/query`;
  const body: Record<string, unknown> = {
    startDate: input.startDate,
    endDate: input.endDate,
    dimensions: input.dimensions,
    type: input.type ?? "web",
    rowLimit: input.rowLimit ?? 1000,
    startRow: input.startRow ?? 0,
    dataState: input.dataState ?? "final",
    aggregationType: input.aggregationType ?? "auto",
  };
  if (input.filters?.length) {
    body.dimensionFilterGroups = [{ groupType: "and", filters: input.filters }];
  }
  return gscJson<GscQueryResponse>(url, accessToken, { method: "POST", body: JSON.stringify(body) });
}

export async function inspectGscUrl(accessToken: string, propertyUrl: string, inspectionUrl: string, languageCode = "en-US") {
  return gscJson<{ inspectionResult?: Record<string, unknown> }>(
    "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
    accessToken,
    {
      method: "POST",
      body: JSON.stringify({ inspectionUrl, siteUrl: propertyUrl, languageCode }),
    },
  );
}

export async function listGscSitemaps(accessToken: string, propertyUrl: string, sitemapIndex?: string) {
  const url = new URL(`https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(propertyUrl)}/sitemaps`);
  if (sitemapIndex) url.searchParams.set("sitemapIndex", sitemapIndex);
  return gscJson<{ sitemap?: Array<Record<string, unknown>> }>(url.toString(), accessToken);
}
