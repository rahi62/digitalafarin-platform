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
    body.dimensionFilterGroups = [{
      groupType: "and",
      filters: input.filters,
    }];
  }

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
      "Content-Type": "application/json",
      "User-Agent": "DigitalAfarin-WordPress-MCP/0.5",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  const data = await response.json().catch(() => null) as (GscQueryResponse & { error?: { message?: string } }) | null;
  if (!response.ok || !data) {
    throw new GscApiError(data?.error?.message || `Search Console API returned HTTP ${response.status}`, response.status);
  }
  return data;
}
