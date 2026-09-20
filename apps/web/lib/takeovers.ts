import type { ServiceLifecycle } from "./service-adoption";

export type TakeoverState =
  | "queued"
  | "inspecting"
  | "preparing"
  | "prepared"
  | "activating"
  | "verifying"
  | "succeeded"
  | "failed"
  | "rolled_back"
  | "rollback_failed"
  | "canceled";

const EXACT_COMMIT = /^[0-9a-f]{40}$/;

export function buildPrepareTakeoverRequest(commit: string) {
  const normalized = commit.trim();
  if (!EXACT_COMMIT.test(normalized)) {
    throw new Error("Exact lowercase 40-character commit is required.");
  }
  return { commit: normalized };
}

export function canPrepareTakeover(lifecycle: ServiceLifecycle) {
  return lifecycle === "configured";
}

export function canActivateTakeover(state: TakeoverState) {
  return state === "prepared";
}

export function takeoverStateLabel(state: TakeoverState) {
  const labels: Record<TakeoverState, string> = {
    queued: "Queued",
    inspecting: "Inspecting",
    preparing: "Preparing release",
    prepared: "Prepared · No cutover yet",
    activating: "Activating",
    verifying: "Verifying health",
    succeeded: "Succeeded · Managed",
    failed: "Failed · Unmanaged",
    rolled_back: "Rolled back · Unmanaged",
    rollback_failed: "Rollback failed · Intervention required",
    canceled: "Canceled",
  };
  return labels[state];
}
