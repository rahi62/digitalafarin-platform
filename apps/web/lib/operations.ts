export type ServiceAction = "start" | "stop" | "restart";

const unitPattern = /^[A-Za-z0-9_.@:-]+\.service$/;

export function buildServiceOperation(
  serverId: string,
  action: ServiceAction,
  unitName: string,
  idempotencyKey: string,
) {
  if (!(["start", "stop", "restart"] as string[]).includes(action)) {
    throw new Error("Unsupported service action");
  }
  if (!unitPattern.test(unitName)) throw new Error("Invalid service unit");
  return {
    server_id: serverId,
    kind: `service.${action}`,
    payload: { unit_name: unitName },
    idempotency_key: idempotencyKey,
  };
}
