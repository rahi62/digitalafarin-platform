import type { GscQueryResponse } from "./gsc.js";

type Row = NonNullable<GscQueryResponse["rows"]>[number];
export type GscComparison = {
  keys: string[];
  previous: { clicks: number; impressions: number; ctr: number; position: number } | null;
  current: { clicks: number; impressions: number; ctr: number; position: number } | null;
  delta: { clicks: number; impressions: number; ctrPercentagePoints: number; position: number };
};
const metrics = (row: Row) => ({
  clicks: row.clicks ?? 0,
  impressions: row.impressions ?? 0,
  ctr: row.ctr ?? 0,
  position: row.position ?? 0,
});
const rowKey = (row: Row) => JSON.stringify(row.keys ?? []);
export function compareGscRows(previous: GscQueryResponse, current: GscQueryResponse): GscComparison[] {
  const before = new Map((previous.rows ?? []).map((row) => [rowKey(row), row]));
  const after = new Map((current.rows ?? []).map((row) => [rowKey(row), row]));
  const all = new Set([...before.keys(), ...after.keys()]);
  return [...all].map((key) => {
    const prev = before.get(key);
    const curr = after.get(key);
    const a = metrics(prev ?? {});
    const b = metrics(curr ?? {});
    return {
      keys: JSON.parse(key) as string[],
      previous: prev ? a : null,
      current: curr ? b : null,
      delta: {
        clicks: b.clicks - a.clicks,
        impressions: b.impressions - a.impressions,
        ctrPercentagePoints: (b.ctr - a.ctr) * 100,
        position: curr && prev ? b.position - a.position : 0,
      },
    };
  });
}
